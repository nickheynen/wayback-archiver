import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import argparse
import json
from datetime import datetime
import logging
import os
import configparser
from urllib.robotparser import RobotFileParser
from typing import List, Set, Dict, Optional, Union, Any
from collections import deque
import re
import pathlib
import secrets
from ratelimit import limits, sleep_and_retry
import validators
import urllib.parse
from cachetools import TTLCache
import dns.resolver
import functools

# Setup logging configuration once at module level
logger = logging.getLogger("wayback_archiver")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler('wayback_archiver.log')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console_handler)

class WaybackArchiver:
    # Common image file extensions
    IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff', '.tif']
    
    def __init__(self, subdomain: str, email: Optional[str]=None, delay: int=15, 
                exclude_patterns: Optional[List[str]]=None, max_retries: int=3, 
                backoff_factor: float=1.5, batch_size: int=150, batch_pause: int=180,
                respect_robots_txt: bool=True, https_only: bool=True, 
                s3_access_key: Optional[str]=None, s3_secret_key: Optional[str]=None,
                exclude_images: bool=True, max_depth: int=10, 
                connect_timeout: int=10, read_timeout: int=30, max_session_errors: int=50):
        """
        Initialize the WaybackArchiver instance with the target subdomain and configuration options.

        Args:
            subdomain (str): The full subdomain URL to archive (e.g., 'https://blog.example.com').
            email (str, optional): Email address for the Wayback Machine API. Recommended for high-volume archiving.
            delay (int, optional): Delay in seconds between API requests to avoid rate-limiting (default: 15 seconds).
            exclude_patterns (list, optional): List of URL patterns to exclude from crawling (e.g., ['/tag/', '/category/']).
            max_retries (int, optional): Maximum number of retry attempts for failed archive requests (default: 3).
            backoff_factor (float, optional): Exponential backoff factor for retries (default: 1.5).
            batch_size (int, optional): Number of URLs to process before taking a longer pause (default: 150).
            batch_pause (int, optional): Duration in seconds to pause between batches (default: 180 seconds).
            respect_robots_txt (bool, optional): Whether to respect robots.txt directives (default: True).
            https_only (bool, optional): Whether to only crawl and archive HTTPS URLs (default: True).
            s3_access_key (str, optional): Internet Archive S3 access key for authentication.
            s3_secret_key (str, optional): Internet Archive S3 secret key for authentication.
            exclude_images (bool, optional): Whether to exclude image files from archiving (default: True).
            max_depth (int, optional): Maximum crawl depth from the starting URL (default: 10).
            connect_timeout (int, optional): Connection timeout in seconds (default: 10).
            read_timeout (int, optional): Read timeout in seconds (default: 30).
            max_session_errors (int, optional): Maximum number of session errors before recreating the session (default: 50).
        """
        # Validate the subdomain URL format
        if not re.match(r'^https?://', subdomain):
            raise ValueError("Subdomain must start with http:// or https://")
        
        self.subdomain = subdomain
        self.base_domain = urlparse(subdomain).netloc
        self.email = email
        self.delay = max(1, delay)  # Ensure delay is at least 1 second
        self.exclude_patterns = exclude_patterns or []
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.batch_size = batch_size
        self.batch_pause = batch_pause
        self.visited_urls: Set[str] = set()
        self.urls_to_archive: Set[str] = set()
        self.successful_urls: Set[str] = set()
        self.respect_robots_txt = respect_robots_txt
        self.https_only = https_only
        self.s3_access_key = s3_access_key
        self.s3_secret_key = s3_secret_key
        self.exclude_images = exclude_images
        self.robots_parsers: Dict[str, RobotFileParser] = {}  # Cache for robots.txt parsers
        self.max_depth = max_depth
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.error_count = 0
        self.max_session_errors = max_session_errors
        
        # Create a session with connection pooling and retry mechanism
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            max_retries=max_retries,  # Use the user-provided max_retries
            pool_connections=100,
            pool_maxsize=100
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Add caching
        self.robots_cache = TTLCache(maxsize=100, ttl=3600)  # 1 hour TTL
        self.dns_cache = TTLCache(maxsize=100, ttl=300)  # 5 minutes TTL
        
        logger.info("WaybackArchiver initialized.")
        if self.respect_robots_txt:
            logger.info("Robots.txt support enabled.")
        if self.https_only:
            logger.info("HTTPS-only mode enabled. HTTP URLs will be skipped.")
        if self.exclude_images:
            logger.info("Image exclusion enabled. Image files will be skipped.")
        if self.max_depth:
            logger.info(f"Maximum crawl depth set to {self.max_depth}.")
        
        if self.s3_access_key and self.s3_secret_key:
            logger.info("Using Internet Archive S3 API authentication.")
        
    def _get_robots_parser(self, url: str) -> RobotFileParser:
        """
        Fetch and parse the robots.txt file for a given URL's domain.
        
        Args:
            url (str): The URL to get the robots.txt parser for.
            
        Returns:
            RobotFileParser: The parser for the domain's robots.txt.
        """
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Check if we already have a parser for this domain
        if base_url in self.robots_parsers:
            return self.robots_parsers[base_url]
        
        # Create a new parser
        rp = RobotFileParser()
        robots_url = f"{base_url}/robots.txt"
        
        try:
            print(f"Fetching robots.txt from {robots_url}")
            response = self.session.get(robots_url, timeout=30)
            if response.status_code == 200:
                rp.parse(response.text.splitlines())
                logger.info(f"Successfully parsed robots.txt from {robots_url}")
            else:
                logger.warning(f"Failed to fetch robots.txt from {robots_url}: Status code {response.status_code}")
                # If we can't fetch robots.txt, assume everything is allowed
                rp.allow_all = True
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"Connection error fetching robots.txt from {robots_url}: {str(ce)}")
            # If there's a connection error, assume everything is allowed
            rp.allow_all = True
        except requests.exceptions.Timeout as te:
            logger.error(f"Timeout fetching robots.txt from {robots_url}: {str(te)}")
            # If there's a timeout, assume everything is allowed
            rp.allow_all = True
        except Exception as e:
            logger.error(f"Error fetching robots.txt from {robots_url}: {str(e)}")
            # If there's an error, assume everything is allowed
            rp.allow_all = True
        
        # Cache the parser
        self.robots_parsers[base_url] = rp
        return rp
        
    def _is_url_allowed(self, url: str) -> bool:
        """
        Check if a URL is allowed by the domain's robots.txt.
        
        Args:
            url (str): The URL to check.
            
        Returns:
            bool: True if the URL is allowed, False otherwise.
        """
        if not self.respect_robots_txt:
            return True
            
        user_agent = "Wayback_Machine_Subdomain_Archiver"
        parser = self._get_robots_parser(url)
        allowed = parser.can_fetch(user_agent, url)
        
        if not allowed:
            logger.info(f"URL {url} disallowed by robots.txt")
            print(f"Skipping {url} (disallowed by robots.txt)")
            
        return allowed

    def _should_process_url(self, url: str) -> bool:
        """
        Check if a URL should be processed based on various criteria.
        
        Args:
            url (str): The URL to check.
            
        Returns:
            bool: True if the URL should be processed, False otherwise.
        """
        # Skip already visited URLs
        if url in self.visited_urls:
            return False
            
        # Parse the URL
        parsed_url = urlparse(url)
        
        # Skip URLs outside our domain
        if parsed_url.netloc != self.base_domain:
            return False
            
        # Skip non-HTTPS URLs if https_only is enabled
        if self.https_only and parsed_url.scheme != 'https':
            print(f"Skipping non-HTTPS URL: {url}")
            return False
            
        # Skip image files if exclude_images is enabled
        if self.exclude_images and self._is_image_url(url):
            print(f"Skipping image file: {url}")
            self.visited_urls.add(url)  # Mark as visited to avoid revisiting
            return False
            
        # Check if URL should be excluded based on patterns
        for pattern in self.exclude_patterns:
            if pattern in parsed_url.path:
                return False
                
        # Check robots.txt rules
        if self.respect_robots_txt and not self._is_url_allowed(url):
            return False
            
        return True

    def _extract_links(self, html_content: str, base_url: str) -> List[str]:
        """
        Extract all links from an HTML page.
        
        Args:
            html_content (str): The HTML content to parse.
            base_url (str): The base URL to resolve relative links against.
            
        Returns:
            list: A list of absolute URLs found in the HTML.
        """
        links = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Use a timeout to prevent ReDoS attacks with complex HTML
        max_parse_time = 5  # 5 seconds timeout
        start_time = time.time()
        
        # Validate base URL
        if not self._is_valid_url(base_url):
            logger.warning(f"Invalid base URL: {base_url}")
            return links
        
        try:
            for link in soup.find_all('a', href=True):
                # Check timeout
                if time.time() - start_time > max_parse_time:
                    logger.warning(f"Link extraction timeout for {base_url}")
                    break
                    
                href = link['href']
                # Skip javascript: and data: URLs
                if href.startswith(('javascript:', 'data:', 'vbscript:')):
                    continue
                    
                full_url = urljoin(base_url, href)
                
                # Validate the URL
                if not self._is_valid_url(full_url):
                    continue
                
                # Exclude anchor links (keep the base URL part)
                if '#' in full_url:
                    fragment_index = full_url.find('#')
                    full_url = full_url[:fragment_index]
                    if not full_url:
                        continue
                        
                links.append(full_url)
        except Exception as e:
            logger.error(f"Error extracting links from {base_url}: {str(e)}")
            
        return links
        
    def _is_valid_url(self, url: str) -> bool:
        """
        Validate URL format and safety.
        
        Args:
            url (str): URL to validate
            
        Returns:
            bool: True if URL is valid and safe, False otherwise
        """
        try:
            if not validators.url(url):
                return False
                
            parsed = urlparse(url)
            
            # Additional security checks
            if any(c in url for c in ['<', '>', '"', '{', '}', '|', '\\', '^', '`']):
                return False
                
            # Check for javascript: protocol variants
            if re.match(r'^javascript:', parsed.scheme, re.IGNORECASE):
                return False
                
            # Must have a hostname
            if not parsed.netloc:
                return False
                
            # Prevent localhost and private network access
            hostname = parsed.netloc.split(':')[0].lower()
            if (hostname == 'localhost' or 
                hostname.startswith('127.') or 
                hostname.startswith('192.168.') or
                hostname.startswith('10.') or
                (hostname.startswith('172.') and 16 <= int(hostname.split('.')[1]) <= 31)):
                return False
                
            # Add a maximum URL length to prevent attacks
            if len(url) > 2048:
                return False
                
            return True
        except Exception:
            return False
        
    def _is_image_url(self, url: str) -> bool:
        """
        Check if a URL points to an image file by extension or content type.
        
        Args:
            url (str): The URL to check.
            
        Returns:
            bool: True if the URL points to an image file, False otherwise.
        """
        parsed_url = urlparse(url)
        path_lower = parsed_url.path.lower()
        
        # Check if the URL ends with an image extension
        for ext in self.IMAGE_EXTENSIONS:
            if path_lower.endswith(ext):
                return True
                
        # Check for image query parameters (common in CDNs)
        if re.search(r'\.(jpe?g|png|gif|bmp|svg|webp|ico|tiff?)([?&]|$)', path_lower):
            return True
                
        return False

    def crawl(self, max_pages: Optional[int]=None) -> None:
        """
        Crawl the subdomain to discover all URLs within the same domain using an iterative, 
        breadth-first approach to avoid recursion issues.

        Args:
            max_pages (int, optional): Maximum number of pages to crawl. If None, crawl all pages (default: None).
        """
        logger.info(f"Starting to crawl {self.subdomain}")
        print(f"Starting to crawl {self.subdomain}")
        
        # Queue for BFS crawling with (url, depth) tuples
        queue = deque([(self.subdomain, 0)])
        
        try:
            while queue and (max_pages is None or len(self.visited_urls) < max_pages):
                url, depth = queue.popleft()
                
                # Skip this URL if it shouldn't be processed
                if not self._should_process_url(url):
                    continue
                    
                # Check max depth
                if depth > self.max_depth:
                    continue
                
                # Mark as visited and add to archive list
                self.visited_urls.add(url)
                self.urls_to_archive.add(url)
                
                try:
                    print(f"Crawling: {url} (depth {depth}/{self.max_depth})")
                    response = self.session.get(url, timeout=30)
                    
                    if response.status_code != 200:
                        logger.warning(f"Failed to fetch {url}: Status code {response.status_code}")
                        print(f"Failed to fetch {url}: Status code {response.status_code}")
                        continue
                    
                    # Only process HTML content    
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' not in content_type.lower():
                        continue
                        
                    # Extract links and add to queue
                    links = self._extract_links(response.text, url)
                    for link in links:
                        if link not in self.visited_urls:
                            queue.append((link, depth + 1))
                            
                except requests.exceptions.ConnectionError as ce:
                    logger.error(f"Connection error crawling {url}: {str(ce)}")
                    print(f"Connection error crawling {url}: {str(ce)}")
                except requests.exceptions.Timeout as te:
                    logger.error(f"Timeout error crawling {url}: {str(te)}")
                    print(f"Timeout error crawling {url}: {str(te)}")
                except requests.exceptions.RequestException as re:
                    logger.error(f"Request error crawling {url}: {str(re)}")
                    print(f"Request error crawling {url}: {str(re)}")
                except Exception as e:
                    logger.error(f"Error crawling {url}: {str(e)}")
                    print(f"Error crawling {url}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error during crawling: {str(e)}")
            print(f"Error during crawling: {str(e)}")
            
        logger.info(f"Crawling completed. Found {len(self.urls_to_archive)} URLs to archive.")
        print(f"Crawling completed. Found {len(self.urls_to_archive)} URLs to archive.")
    
    def archive_urls(self) -> None:
        """
        Submit all discovered URLs to the Wayback Machine for archiving.

        This method processes URLs in batches to ensure API politeness and handles retries for failed requests.
        """
        if not self.urls_to_archive:
            logger.warning("No URLs to archive. Run crawl() first.")
            print("No URLs to archive. Run crawl() first.")
            return
            
        logger.info(f"Starting to archive {len(self.urls_to_archive)} URLs")
        print(f"Starting to archive {len(self.urls_to_archive)} URLs")
        print(f"Using a {self.delay}s delay between requests and a {self.batch_pause}s pause after every {self.batch_size} URLs")
        
        # Keep track of failed URLs for retry
        failed_urls = []
        urls_list = list(self.urls_to_archive)
        
        try:
            for i, url in enumerate(urls_list):
                # Check if we need to take a batch pause
                if i > 0 and i % self.batch_size == 0:
                    batch_num = i // self.batch_size
                    logger.info(f"Completed batch {batch_num}. Taking a {self.batch_pause}s pause...")
                    print(f"\nCompleted batch {batch_num}. Taking a longer pause of {self.batch_pause} seconds...")
                    try:
                        time.sleep(self.batch_pause)
                    except KeyboardInterrupt:
                        logger.warning("User interrupted batch pause. Continuing with next URL.")
                        print("\nPause interrupted. Continuing...")
                    print(f"Resuming with the next batch of URLs ({i+1} to {min(i+self.batch_size, len(urls_list))})...\n")
                    
                try:
                    success = self._archive_url(url, max_retries=self.max_retries, backoff_factor=self.backoff_factor)
                    if success:
                        self.successful_urls.add(url)
                        logger.info(f"Archived successfully: {url}")
                        print(f"[{i+1}/{len(self.urls_to_archive)}] Archived: {url}")
                    else:
                        logger.warning(f"Failed to archive after retries: {url}")
                        print(f"[{i+1}/{len(self.urls_to_archive)}] Failed after retries: {url}")
                        failed_urls.append(url)
                    
                    # Regular delay between requests
                    if i < len(urls_list) - 1:  # Don't sleep after the last URL
                        time.sleep(self.delay)
                        
                except Exception as e:
                    logger.error(f"Error archiving {url}: {str(e)}")
                    print(f"Error archiving {url}: {str(e)}")
                    failed_urls.append(url)
                    
        except KeyboardInterrupt:
            logger.warning("Archiving process interrupted by user.")
            print("\nArchiving process interrupted by user.")
        finally:
            # Always save results, even on interruption
            self._save_results(failed_urls)
    
    def _save_results(self, failed_urls: List[str]) -> None:
        """
        Save both successful and failed URLs to JSON files.
        
        Args:
            failed_urls (list): List of URLs that failed to archive.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize domain name to prevent directory traversal or special chars
        domain_name = re.sub(r'[^a-zA-Z0-9_]', '_', self.base_domain)
        output_dir = pathlib.Path("wayback_results")
        
        # Create output directory if it doesn't exist with secure permissions
        try:
            output_dir.mkdir(exist_ok=True)
            # Set secure file permissions (0o750 = rwxr-x---)
            os.chmod(output_dir, 0o750)
        except Exception as e:
            logger.error(f"Failed to create output directory: {str(e)}")
            print(f"Failed to create output directory: {str(e)}")
            # Fall back to current directory
            output_dir = pathlib.Path(".")
            
        # Generate unique filenames with random component to prevent enumeration
        random_suffix = secrets.token_hex(4)
        
        # Save successful URLs
        if self.successful_urls:
            success_file = output_dir / f"successful_urls_{domain_name}_{timestamp}_{random_suffix}.json"
            try:
                # Use a secure temp file first, then rename atomically
                temp_file = output_dir / f".tmp_{secrets.token_hex(8)}.json"
                with open(temp_file, 'w') as f:
                    json.dump({
                        "domain": self.base_domain,
                        "timestamp": timestamp,
                        "total_urls": len(self.urls_to_archive),
                        "successful_urls": list(self.successful_urls)
                    }, f, indent=2)
                
                # Set secure file permissions before renaming
                os.chmod(temp_file, 0o640)  # 0o640 = rw-r-----
                os.rename(temp_file, success_file)
                
                logger.info(f"Successfully archived URLs saved to {success_file}")
                print(f"Successfully archived URLs saved to {success_file}")
            except Exception as e:
                logger.error(f"Error saving successful URLs to file: {str(e)}")
                print(f"Error saving successful URLs to file: {str(e)}")
                # Clean up temp file if it exists
                if 'temp_file' in locals() and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                
        # Save failed URLs if any
        if failed_urls:
            logger.warning(f"{len(failed_urls)} URLs failed to archive after retries.")
            print(f"\n{len(failed_urls)} URLs failed to archive after retries.")
            
            # Save failed URLs to a JSON file for future retry
            failed_file = output_dir / f"failed_urls_{domain_name}_{timestamp}_{random_suffix}.json"
            
            try:
                # Use a secure temp file first, then rename atomically
                temp_file = output_dir / f".tmp_{secrets.token_hex(8)}.json"
                with open(temp_file, 'w') as f:
                    json.dump({
                        "domain": self.base_domain,
                        "timestamp": timestamp,
                        "total_urls": len(self.urls_to_archive),
                        "failed_urls": failed_urls
                    }, f, indent=2)
                
                # Set secure file permissions before renaming
                os.chmod(temp_file, 0o640)  # 0o640 = rw-r-----
                os.rename(temp_file, failed_file)
                
                logger.info(f"Failed URLs saved to {failed_file} for future retry.")
                print(f"Failed URLs have been saved to {failed_file} for future retry.")
            except Exception as e:
                logger.error(f"Error saving failed URLs to file: {str(e)}")
                print(f"Error saving failed URLs to file: {str(e)}")
                # Clean up temp file if it exists
                if 'temp_file' in locals() and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
    
    def _calculate_wait_time(self, retry_delay: float, backoff_factor: float, retries: int) -> float:
        """
        Calculate the wait time for a retry attempt with exponential backoff.
        
        Args:
            retry_delay (float): Base delay time in seconds
            backoff_factor (float): Backoff multiplier
            retries (int): Current retry attempt (0-based)
            
        Returns:
            float: Wait time in seconds
        """
        return retry_delay * (backoff_factor ** retries)

    def _handle_retry(self, url: str, error_type: str, error_msg: str, 
                   retry_delay: float, backoff_factor: float, 
                   retries: int, max_retries: int) -> None:
        """
        Handle a retry situation with appropriate logging and delay.
        
        Args:
            url (str): The URL being archived
            error_type (str): Type of error for reporting
            error_msg (str): Detailed error message
            retry_delay (float): Base delay for retries
            backoff_factor (float): Backoff multiplier
            retries (int): Current retry count
            max_retries (int): Maximum number of retries
        """
        wait_time = self._calculate_wait_time(retry_delay, backoff_factor, retries)
        logger.warning(f"{error_type} for {url}: {error_msg}")
        print(f"{error_type}. Waiting {wait_time:.1f}s before retry {retries+1}/{max_retries}...")
        
        try:
            time.sleep(wait_time)
        except KeyboardInterrupt:
            print("\nRetry wait interrupted by user. Continuing immediately...")

    @sleep_and_retry
    @limits(calls=1, period=15)  # Enforce rate limiting
    def _archive_url(self, url: str, max_retries: int=3, retry_delay: Optional[float]=None, 
                    backoff_factor: float=1.5) -> bool:
        """
        Submit a single URL to the Wayback Machine's Save Page Now service with retry logic.

        Args:
            url (str): The URL to archive.
            max_retries (int, optional): Maximum number of retry attempts for failed requests (default: 3).
            retry_delay (float, optional): Delay in seconds between retries. Defaults to the instance's delay setting.
            backoff_factor (float, optional): Multiplier for exponential backoff between retries (default: 1.5).

        Returns:
            bool: True if the URL was archived successfully, False otherwise.
        """
        # Sanitize and validate URL
        try:
            sanitized_url = urllib.parse.quote(url, safe=':/?=&')
            if not validators.url(sanitized_url):
                logger.error(f"Invalid URL format: {url}")
                return False
        except Exception as e:
            logger.error(f"URL sanitation error: {str(e)}")
            return False

        if retry_delay is None:
            retry_delay = self.delay
            
        api_url = "https://web.archive.org/save"
        
        # Parameters for the Wayback Machine API
        # Documentation: https://archive.org/help/wayback_api.php
        params = {
            'url': url,
            'capture_all': '1',  # Capture page with all of its requisites
            'capture_outlinks': '0',  # Don't capture outlinks
            'delay': '1',  # Seconds of delay between requests for requisites
            'if_not_archived_within': '432000'  # Only archive if not captured in the last 5 days (5*24*60*60=432000)
        }
        
        # Add authentication parameters
        if self.s3_access_key and self.s3_secret_key:
            params['s3_access_key'] = self.s3_access_key
            params['s3_secret_key'] = self.s3_secret_key
        elif self.email:
            params['email'] = self.email
            
        headers = {
            'User-Agent': 'Wayback_Machine_Subdomain_Archiver/1.1 (Python; respect@archive.org)',
            'From': self.email if self.email else 'anonymous_archiver@example.com'
        }
        
        retries = 0
        while retries <= max_retries:
            try:
                # Use the class session with persistent connection pool and DNS cache
                response = self.session.post(api_url, params=params, headers=headers, timeout=(self.connect_timeout, self.read_timeout))
                if response.status_code in [200, 201]:
                    logger.info(f"URL archived successfully: {url}")
                    return True
                else:
                    error_type = "Rate limit exceeded" if response.status_code == 429 else \
                        f"Server error ({response.status_code})" if response.status_code >= 500 else \
                        f"API error ({response.status_code})"
                    error_msg = response.text
                    self._handle_retry(url, error_type, error_msg, retry_delay, backoff_factor, retries, max_retries)
            except requests.exceptions.ConnectionError as e:
                self._handle_retry(url, "Connection error", str(e), retry_delay, backoff_factor, retries, max_retries)
            except requests.exceptions.Timeout as e:
                self._handle_retry(url, "Request timeout", str(e), retry_delay, backoff_factor, retries, max_retries)
            except requests.exceptions.RequestException as e:
                self._handle_retry(url, "Request error", str(e), retry_delay, backoff_factor, retries, max_retries)
            except Exception as e:
                self._handle_retry(url, "Unexpected error", str(e), retry_delay, backoff_factor, retries, max_retries)
            retries += 1
        
        return False  # Failed after all retries

    def _check_session_health(self):
        """Monitor session health and recreate if needed."""
        if self.error_count > self.max_session_errors:
            logger.warning("Session error threshold reached, recreating session")
            self.session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                max_retries=self.max_retries,
                pool_connections=100,
                pool_maxsize=100
            )
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)
            self.error_count = 0

    @functools.lru_cache(maxsize=100)
    def _resolve_domain(self, domain: str) -> Optional[str]:
        """Cache DNS resolutions."""
        try:
            return str(dns.resolver.resolve(domain, 'A')[0])
        except Exception as e:
            logger.error(f"DNS resolution error for {domain}: {str(e)}")
            return None

def _load_s3_credentials(args) -> tuple:
    """
    Load S3 credentials from the specified source.
    
    Args:
        args: The parsed command-line arguments.
        
    Returns:
        tuple: (access_key, secret_key) or (None, None) if not available
    """
    # Option 1: Direct command line arguments (least secure)
    if args.s3_access_key and args.s3_secret_key:
        logger.warning("Using S3 credentials from command line is less secure. Consider using environment variables or a config file.")
        return args.s3_access_key, args.s3_secret_key
        
    # Option 2: Environment variables
    if args.use_env_keys:
        access_key = os.environ.get('IA_S3_ACCESS_KEY')
        secret_key = os.environ.get('IA_S3_SECRET_KEY')
        if not access_key or not secret_key:
            logger.error("Environment variables IA_S3_ACCESS_KEY and/or IA_S3_SECRET_KEY not found.")
            print("Error: Environment variables IA_S3_ACCESS_KEY and/or IA_S3_SECRET_KEY not set.")
            return None, None
            
        logger.info("Using S3 credentials from environment variables.")
        return access_key, secret_key
        
    # Option 3: Configuration file
    if args.config_file:
        if not os.path.exists(args.config_file):
            logger.error(f"Config file not found: {args.config_file}")
            print(f"Error: Config file not found: {args.config_file}")
            return None, None
            
        try:
            config = configparser.ConfigParser()
            config.read(args.config_file)
            access_key = config.get('default', 's3_access_key')
            secret_key = config.get('default', 's3_secret_key')
            logger.info(f"Using S3 credentials from config file: {args.config_file}")
            return access_key, secret_key
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            logger.error(f"Error reading config file: {str(e)}")
            print(f"Error reading config file: {str(e)}")
            print("Config file should have format:\n[default]\ns3_access_key = YOUR_KEY\ns3_secret_key = YOUR_SECRET")
            return None, None
            
    return None, None

def _load_retry_urls(retry_file: str) -> list:
    """
    Load URLs to retry from a JSON file.
    
    Args:
        retry_file (str): Path to the JSON file containing failed URLs
        
    Returns:
        list: List of URLs to retry, or empty list if none found
    """
    try:
        # Security: Normalize path and validate it's in the expected directory
        retry_file_path = os.path.abspath(os.path.normpath(retry_file))
        app_dir = os.path.abspath(os.path.dirname(__file__))
        expected_dir = os.path.join(app_dir, "wayback_results")
        
        # Ensure file is within the expected directory or current directory
        if not (retry_file_path.startswith(app_dir) or 
                retry_file_path.startswith(expected_dir) or
                os.path.dirname(retry_file_path) == os.getcwd()):
            logger.error(f"Security error: Retry file path outside of allowed directories: {retry_file}")
            print(f"Error: Retry file must be in the application directory or wayback_results directory")
            return []
            
        if not os.path.exists(retry_file_path):
            logger.error(f"Retry file not found: {retry_file}")
            print(f"Error: Retry file not found: {retry_file}")
            return []
            
        # Limit file size to prevent memory issues
        file_size = os.path.getsize(retry_file_path)
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            logger.error(f"Retry file too large (>{file_size/1024/1024:.2f}MB): {retry_file}")
            print(f"Error: Retry file too large (max 10MB)")
            return []
            
        with open(retry_file_path, 'r') as f:
            # Use strict=False to prevent JSON vulnerability exploits
            retry_data = json.loads(f.read(), strict=False)
            urls_to_retry = retry_data.get('failed_urls', [])
            
            # Validate URLs
            valid_urls = []
            for url in urls_to_retry:
                # Basic URL validation
                parsed = urlparse(url)
                if parsed.scheme in ('http', 'https') and parsed.netloc:
                    valid_urls.append(url)
                else:
                    logger.warning(f"Skipping invalid URL in retry file: {url}")
                    
        if not valid_urls:
            logger.warning(f"No valid URLs found to retry in {retry_file}")
            print(f"No valid URLs found to retry in {retry_file}")
            
        return valid_urls
        
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON format in retry file: {retry_file}")
        print(f"Error: Invalid JSON format in retry file: {retry_file}")
    except Exception as e:
        logger.error(f"Error loading retry file: {str(e)}")
        print(f"Error loading retry file: {str(e)}")
        
    return []

def main():
    """
    Parse command-line arguments and execute the WaybackArchiver process.

    This function supports both normal crawling and retrying previously failed URLs.
    """
    parser = argparse.ArgumentParser(description='Archive an entire subdomain using the Wayback Machine')
    # Add the -f argument
    parser.add_argument('-f', '--file', help='Text file containing URLs to archive (one per line)')
    # Make subdomain optional if using -f
    parser.add_argument('subdomain', nargs='?', help='The subdomain to archive (e.g., https://blog.example.com)')
    parser.add_argument('--email', help='Your email address (recommended for API use and necessary for high volume archiving)')
    parser.add_argument('--delay', type=int, default=15, help='Delay between archive requests in seconds (default: 15, minimum recommended is 10)')
    parser.add_argument('--max-pages', type=int, help='Maximum number of pages to crawl (default: unlimited)')
    parser.add_argument('--max-retries', type=int, default=3, help='Maximum retry attempts for failed archives (default: 3)')
    parser.add_argument('--backoff-factor', type=float, default=1.5, help='Exponential backoff factor for retries (default: 1.5)')
    parser.add_argument('--max-depth', type=int, default=10, help='Maximum crawl depth from starting URL (default: 10)')
    parser.add_argument('--batch-size', type=int, default=150, help='Process URLs in batches of this size and pause between batches (default: 150)')
    parser.add_argument('--batch-pause', type=int, default=180, help='Seconds to pause between batches (default: 180)')
    parser.add_argument('--exclude', nargs='+', 
                      default=['/tag/', '/category/', '/author/', '/page/', '/comment-page-', 
                               '/wp-json/', '/feed/', '/wp-content/cache/', '/wp-admin/',
                               '/search/', '/login/', '/register/', '/signup/', '/logout/', 
                               '/privacy-policy/', '/terms-of-service/', '/404/', '/error/'],
                      help='URL patterns to exclude (WordPress defaults and common patterns: /tag/, /category/, etc.)')
    parser.add_argument('--retry-file', help='JSON file containing previously failed URLs to retry')
    parser.add_argument('--ignore-robots-txt', action='store_true', help='Ignore robots.txt directives (not recommended)')
    parser.add_argument('--include-http', action='store_true', help='Include HTTP URLs in addition to HTTPS (not recommended)')
    parser.add_argument('--include-images', action='store_true', help='Include image files in archiving (default: exclude images)')
    parser.add_argument('--s3-access-key', help='Internet Archive S3 access key for authentication (not recommended, use --use-env-keys or --config-file instead)')
    parser.add_argument('--s3-secret-key', help='Internet Archive S3 secret key for authentication (not recommended, use --use-env-keys or --config-file instead)')
    parser.add_argument('--use-env-keys', action='store_true', help='Use S3 credentials from IA_S3_ACCESS_KEY and IA_S3_SECRET_KEY environment variables')
    parser.add_argument('--config-file', help='Path to configuration file containing S3 credentials')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Handle file input
    if args.file:
        try:
            with open(args.file, 'r') as f:
                urls = [line.strip() for line in f if line.strip()]
            logger.info(f"Loaded {len(urls)} URLs from {args.file}")
            print(f"Loaded {len(urls)} URLs from {args.file}")
            
            if not urls:
                logger.error("No valid URLs found in the file")
                print("Error: No valid URLs found in the file")
                return 1
                
            # We'll process multiple URLs from the file
            process_multiple_urls = True
        except Exception as e:
            logger.error(f"Error reading URL file: {str(e)}")
            print(f"Error reading URL file: {str(e)}")
            return 1
    elif not args.subdomain:
        print("Error: Either subdomain or -f/--file argument is required")
        return 1
    else:
        # Single URL mode
        urls = [args.subdomain]
        process_multiple_urls = False
    
    # Set logging level based on verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    # Validate URL formats if we're not reading from a file
    if not args.file:
        if not args.subdomain.startswith(('http://', 'https://')):
            print("Error: Subdomain must start with http:// or https://")
            return 1
    
    # Handle S3 credentials
    s3_access_key, s3_secret_key = _load_s3_credentials(args)
    
    exit_code = 0
    
    try:
        # Check if we're retrying previously failed URLs
        if args.retry_file:
            # Create the archiver using the first URL for basic setup
            try:
                archiver = WaybackArchiver(
                    urls[0], 
                    email=args.email, 
                    delay=args.delay, 
                    exclude_patterns=args.exclude,
                    max_retries=args.max_retries,
                    backoff_factor=args.backoff_factor,
                    batch_size=args.batch_size,
                    batch_pause=args.batch_pause,
                    respect_robots_txt=not args.ignore_robots_txt,
                    https_only=not args.include_http,
                    s3_access_key=s3_access_key,
                    s3_secret_key=s3_secret_key,
                    exclude_images=not args.include_images,
                    max_depth=args.max_depth
                )
            except ValueError as e:
                logger.error(f"Configuration error: {str(e)}")
                print(f"Error: {str(e)}")
                return 1
                
            urls_to_retry = _load_retry_urls(args.retry_file)
            if urls_to_retry:
                print(f"Retrying {len(urls_to_retry)} previously failed URLs from {args.retry_file}")
                archiver.urls_to_archive = set(urls_to_retry)
                archiver.archive_urls()
            else:
                exit_code = 1  # No URLs found to retry
        else:
            # Process each URL in the file (or just the single subdomain)
            for i, url in enumerate(urls):
                if process_multiple_urls:
                    print(f"\n[{i+1}/{len(urls)}] Processing URL: {url}")
                    logger.info(f"Processing URL {i+1}/{len(urls)}: {url}")
                
                # Create a new archiver for each URL
                try:
                    archiver = WaybackArchiver(
                        url, 
                        email=args.email, 
                        delay=args.delay, 
                        exclude_patterns=args.exclude,
                        max_retries=args.max_retries,
                        backoff_factor=args.backoff_factor,
                        batch_size=args.batch_size,
                        batch_pause=args.batch_pause,
                        respect_robots_txt=not args.ignore_robots_txt,
                        https_only=not args.include_http,
                        s3_access_key=s3_access_key,
                        s3_secret_key=s3_secret_key,
                        exclude_images=not args.include_images,
                        max_depth=args.max_depth
                    )
                except ValueError as e:
                    logger.error(f"Configuration error for URL {url}: {str(e)}")
                    print(f"Error with URL {url}: {str(e)}")
                    continue  # Skip to the next URL
                
                # Normal crawl and archive
                archiver.crawl(args.max_pages)
                if not archiver.urls_to_archive:
                    logger.warning(f"No URLs found to archive for {url}. Check your URL and exclusion patterns.")
                    print(f"Warning: No URLs found to archive for {url}. Check your URL and exclusion patterns.")
                else:
                    archiver.archive_urls()
                    print(f"Completed archiving for {url}")
                    logger.info(f"Completed archiving for {url}")
                
                # If there are more URLs to process, take a short break
                if process_multiple_urls and i < len(urls) - 1:
                    pause_time = 5  # 5 seconds pause between processing different domains
                    print(f"Taking a {pause_time} second pause before the next URL...")
                    time.sleep(pause_time)
                
        logger.info("All archiving processes completed!")
        print("\nAll archiving processes completed!")
                
    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Exiting...")
        logger.warning("Process interrupted by user.")
        exit_code = 130  # Standard exit code for interrupt
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
        print(f"An error occurred: {str(e)}")
        exit_code = 1
        
    return exit_code

if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        import sys
        sys.exit(exit_code)