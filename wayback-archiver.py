import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import argparse
import json
from datetime import datetime

class WaybackArchiver:
    def __init__(self, subdomain, email=None, delay=30, exclude_patterns=None, 
                max_retries=3, backoff_factor=2.0, batch_size=100, batch_pause=300):
        """
        Initialize the archiver with the target subdomain
        
        Args:
            subdomain: The full subdomain URL (e.g., 'https://blog.example.com')
            email: Optional email for the Wayback Machine API (recommended but not required)
            delay: Delay between API requests in seconds (default 30s for API politeness)
            exclude_patterns: List of URL patterns to exclude (e.g., ['/tag/', '/category/'])
            max_retries: Maximum number of retry attempts for failed archives
            backoff_factor: Exponential backoff factor for retries
            batch_size: Number of URLs to process before taking a longer pause
            batch_pause: Seconds to pause between batches
        """
        self.subdomain = subdomain
        self.base_domain = urlparse(subdomain).netloc
        self.email = email
        self.delay = delay
        self.exclude_patterns = exclude_patterns or []
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.batch_size = batch_size
        self.batch_pause = batch_pause
        self.visited_urls = set()
        self.urls_to_archive = set()
        
    def crawl(self, max_pages=None):
        """
        Crawl the subdomain to find all URLs
        
        Args:
            max_pages: Maximum number of pages to crawl (None for unlimited)
        """
        print(f"Starting to crawl {self.subdomain}")
        self._crawl_page(self.subdomain, max_pages)
        print(f"Crawling completed. Found {len(self.urls_to_archive)} URLs to archive.")
        
    def _crawl_page(self, url, max_pages=None):
        """
        Recursively crawl a page and extract all links within the same subdomain
        """
        if url in self.visited_urls:
            return
            
        if max_pages is not None and len(self.visited_urls) >= max_pages:
            return
            
        self.visited_urls.add(url)
        self.urls_to_archive.add(url)
        
        try:
            print(f"Crawling: {url}")
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                print(f"Failed to fetch {url}: Status code {response.status_code}")
                return
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all links on the page
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(url, href)
                
                # Exclude anchor links
                if '#' in full_url:
                    continue
                
                # Only follow links within the same subdomain and not in excluded patterns
                parsed_url = urlparse(full_url)
                
                # Check if URL should be excluded based on patterns
                should_exclude = False
                for pattern in self.exclude_patterns:
                    if pattern in parsed_url.path:
                        should_exclude = True
                        break
                
                if parsed_url.netloc == self.base_domain and not should_exclude and full_url not in self.visited_urls:
                    self._crawl_page(full_url, max_pages)
                    
        except Exception as e:
            print(f"Error crawling {url}: {str(e)}")
    
    def archive_urls(self):
        """
        Submit all found URLs to the Wayback Machine
        With batching for API politeness
        """
        if not self.urls_to_archive:
            print("No URLs to archive. Run crawl() first.")
            return
            
        print(f"Starting to archive {len(self.urls_to_archive)} URLs")
        print(f"Using a {self.delay}s delay between requests and a {self.batch_pause}s pause after every {self.batch_size} URLs")
        
        # Keep track of failed URLs for retry
        failed_urls = []
        urls_list = list(self.urls_to_archive)
        
        for i, url in enumerate(urls_list):
            # Check if we need to take a batch pause
            if i > 0 and i % self.batch_size == 0:
                batch_num = i // self.batch_size
                print(f"\nCompleted batch {batch_num}. Taking a longer pause of {self.batch_pause} seconds...")
                time.sleep(self.batch_pause)
                print(f"Resuming with the next batch of URLs ({i+1} to {min(i+self.batch_size, len(urls_list))})...\n")
                
            try:
                success = self._archive_url(url, max_retries=self.max_retries, backoff_factor=self.backoff_factor)
                if success:
                    print(f"[{i+1}/{len(self.urls_to_archive)}] Archived: {url}")
                else:
                    print(f"[{i+1}/{len(self.urls_to_archive)}] Failed after retries: {url}")
                    failed_urls.append(url)
                
                # Regular delay between requests
                if i < len(urls_list) - 1:  # Don't sleep after the last URL
                    time.sleep(self.delay)
                    
            except Exception as e:
                print(f"Error archiving {url}: {str(e)}")
                failed_urls.append(url)
        
        # Report on failed URLs
        if failed_urls:
            print(f"\n{len(failed_urls)} URLs failed to archive after retries.")
            
            # Save failed URLs to a JSON file for future retry
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            domain_name = self.base_domain.replace(".", "_")
            filename = f"failed_urls_{domain_name}_{timestamp}.json"
            
            try:
                with open(filename, 'w') as f:
                    json.dump({
                        "domain": self.base_domain,
                        "timestamp": timestamp,
                        "failed_urls": failed_urls
                    }, f, indent=2)
                print(f"Failed URLs have been saved to {filename} for future retry.")
            except Exception as e:
                print(f"Error saving failed URLs to file: {str(e)}")
    
    def _archive_url(self, url, max_retries=3, retry_delay=None, backoff_factor=2):
        """
        Submit a single URL to the Wayback Machine's Save Page Now service
        With retry logic for temporary failures
        
        Args:
            url: The URL to archive
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Delay between retries in seconds (default: self.delay)
            backoff_factor: Multiplier for delay after each retry (exponential backoff)
            
        Returns:
            bool: True if archiving was successful, False otherwise
        """
        if retry_delay is None:
            retry_delay = self.delay
            
        api_url = "https://web.archive.org/save"
        
        # Parameters for the Wayback Machine API
        # Documentation: https://archive.org/help/wayback_api.php
        params = {
            'url': url,
            'capture_all': '1',  # Capture page with all of its requisites
            'capture_outlinks': '0',  # Don't capture outlinks
            'delay': '2',  # Seconds of delay between requests for requisites
            'if_not_archived_within': '86400'  # Only archive if not captured in the last 24 hours
        }
        
        if self.email:
            params['email'] = self.email
            
        headers = {
            'User-Agent': 'Wayback_Machine_Subdomain_Archiver/1.1 (Python; respect@archive.org)',
            'From': self.email if self.email else 'anonymous_archiver@example.com'
        }
        
        retries = 0
        while retries <= max_retries:
            try:
                response = requests.post(api_url, params=params, headers=headers, timeout=30)
                
                if response.status_code in [200, 201]:
                    return True
                
                # Handle specific error cases
                if response.status_code == 429:  # Too Many Requests
                    wait_time = retry_delay * (backoff_factor ** retries)
                    print(f"Rate limited (429). Waiting {wait_time}s before retry {retries+1}/{max_retries}...")
                    time.sleep(wait_time)
                elif response.status_code >= 500:  # Server errors
                    wait_time = retry_delay * (backoff_factor ** retries)
                    print(f"Server error ({response.status_code}). Waiting {wait_time}s before retry {retries+1}/{max_retries}...")
                    time.sleep(wait_time)
                else:
                    wait_time = retry_delay * (backoff_factor ** retries)
                    print(f"API returned status code {response.status_code}. Waiting {wait_time}s before retry {retries+1}/{max_retries}...")
                    time.sleep(wait_time)
                    
            except requests.exceptions.ConnectionError:
                wait_time = retry_delay * (backoff_factor ** retries)
                print(f"Connection error. Waiting {wait_time}s before retry {retries+1}/{max_retries}...")
                time.sleep(wait_time)
            except requests.exceptions.Timeout:
                wait_time = retry_delay * (backoff_factor ** retries)
                print(f"Request timeout. Waiting {wait_time}s before retry {retries+1}/{max_retries}...")
                time.sleep(wait_time)
            except Exception as e:
                wait_time = retry_delay * (backoff_factor ** retries)
                print(f"Error during archiving: {str(e)}. Waiting {wait_time}s before retry {retries+1}/{max_retries}...")
                time.sleep(wait_time)
                
            retries += 1
            
        return False  # Failed after all retries

def main():
    parser = argparse.ArgumentParser(description='Archive an entire subdomain using the Wayback Machine')
    parser.add_argument('subdomain', help='The subdomain to archive (e.g., https://blog.example.com)')
    parser.add_argument('--email', help='Your email address (recommended for API use and necessary for high volume archiving)')
    parser.add_argument('--delay', type=int, default=30, help='Delay between archive requests in seconds (default: 30, recommended minimum for API politeness)')
    parser.add_argument('--max-pages', type=int, help='Maximum number of pages to crawl (default: unlimited)')
    parser.add_argument('--max-retries', type=int, default=3, help='Maximum retry attempts for failed archives (default: 3)')
    parser.add_argument('--backoff-factor', type=float, default=2.0, help='Exponential backoff factor for retries (default: 2.0)')
    parser.add_argument('--batch-size', type=int, default=100, help='Process URLs in batches of this size and pause between batches (default: 100)')
    parser.add_argument('--batch-pause', type=int, default=300, help='Seconds to pause between batches (default: 300)')
    parser.add_argument('--exclude', nargs='+', 
                      default=['/tag/', '/category/', '/author/', '/page/', '/comment-page-', 
                               '/wp-json/', '/feed/', '/wp-content/cache/', '/wp-admin/',
                               '/search/', '/login/', '/register/', '/signup/', '/logout/', 
                               '/privacy-policy/', '/terms-of-service/', '/404/', '/error/'],
                      help='URL patterns to exclude (WordPress defaults and common patterns: /tag/, /category/, etc.)')
    parser.add_argument('--retry-file', help='JSON file containing previously failed URLs to retry')
    
    args = parser.parse_args()
    
    archiver = WaybackArchiver(
        args.subdomain, 
        email=args.email, 
        delay=args.delay, 
        exclude_patterns=args.exclude,
        max_retries=args.max_retries,
        backoff_factor=args.backoff_factor,
        batch_size=args.batch_size,
        batch_pause=args.batch_pause
    )
    
    try:
        # Check if we're retrying previously failed URLs
        if args.retry_file:
            try:
                with open(args.retry_file, 'r') as f:
                    retry_data = json.load(f)
                    urls_to_retry = retry_data.get('failed_urls', [])
                    
                if urls_to_retry:
                    print(f"Retrying {len(urls_to_retry)} previously failed URLs from {args.retry_file}")
                    archiver.urls_to_archive = set(urls_to_retry)
                    archiver.archive_urls()
                else:
                    print(f"No URLs found to retry in {args.retry_file}")
            except Exception as e:
                print(f"Error loading retry file: {str(e)}")
                return
        else:
            # Normal crawl and archive
            archiver.crawl(args.max_pages)
            archiver.archive_urls()
            
        print("Archiving process completed successfully!")
    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Exiting...")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()