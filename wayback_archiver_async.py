import asyncio
import aiohttp
from typing import Set, List, Optional, Dict, Any
import logging
from wayback_archiver import WaybackArchiver
import aiohttp.client_exceptions
from urllib.parse import urljoin
import re
from bs4 import BeautifulSoup

class AsyncWaybackArchiver(WaybackArchiver):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_concurrent = kwargs.get('max_concurrent', 3)
        self.max_retries = kwargs.get('max_retries', 3)
        self.crawl_depth = kwargs.get('crawl_depth', 1)
        self.session = None
        self.crawled_urls: Set[str] = set()
        self.retry_delays = [1, 5, 15]  # Exponential backoff delays in seconds
        self.conn_limit = kwargs.get('conn_limit', 100)
        self.timeout = aiohttp.ClientTimeout(
            total=60,
            connect=10,
            sock_connect=10,
            sock_read=30
        )

    async def _init_session(self):
        if not self.session:
            connector = aiohttp.TCPConnector(
                limit=self.conn_limit,
                ssl=False,
                use_dns_cache=True,
                ttl_dns_cache=300
            )
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout
            )

    async def _archive_url_async(self, url: str, retry_count: int = 0) -> bool:
        try:
            async with self.session.post(
                "https://web.archive.org/save",
                params=self._get_archive_params(url),
                headers=self._get_headers(),
            ) as response:
                return response.status in [200, 201]
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if retry_count < self.max_retries:
                delay = self.retry_delays[min(retry_count, len(self.retry_delays) - 1)]
                logging.warning(f"Retrying {url} after {delay}s (attempt {retry_count + 1})")
                await asyncio.sleep(delay)
                return await self._archive_url_async(url, retry_count + 1)
            logging.error(f"Error archiving {url} after {self.max_retries} attempts: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error archiving {url}: {str(e)}")
            return False

    async def _crawl_url(self, url: str, depth: int) -> Set[str]:
        if depth <= 0 or url in self.crawled_urls:
            return set()

        self.crawled_urls.add(url)
        found_urls = set()

        try:
            async with self.session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    return found_urls
                
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    full_url = urljoin(url, href)
                    
                    # Only include URLs from the same domain
                    if self._is_same_domain(url, full_url):
                        found_urls.add(full_url)
                        if depth > 1:
                            sub_urls = await self._crawl_url(full_url, depth - 1)
                            found_urls.update(sub_urls)

        except Exception as e:
            logging.error(f"Error crawling {url}: {str(e)}")

        return found_urls

    def _is_same_domain(self, url1: str, url2: str) -> bool:
        domain1 = re.match(r'https?://([^/?#]+)', url1)
        domain2 = re.match(r'https?://([^/?#]+)', url2)
        return domain1 and domain2 and domain1.group(1) == domain2.group(1)

    async def archive_urls_async(self):
        """Archive URLs concurrently with rate limiting and crawling."""
        await self._init_session()
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # First, crawl for additional URLs if depth > 0
        if self.crawl_depth > 0:
            all_urls = set(self.urls_to_archive)
            for url in list(self.urls_to_archive):  # Convert to list to avoid modification during iteration
                crawled_urls = await self._crawl_url(url, self.crawl_depth)
                all_urls.update(crawled_urls)
            self.urls_to_archive = list(all_urls)

        async def archive_with_semaphore(url: str) -> bool:
            async with semaphore:
                await asyncio.sleep(self.delay)  # Rate limiting
                return await self._archive_url_async(url)

        # Create tasks for all URLs
        tasks = [archive_with_semaphore(url) for url in self.urls_to_archive]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for url, result in zip(self.urls_to_archive, results):
            if isinstance(result, Exception):
                logging.error(f"Failed to archive {url}: {str(result)}")
            elif result:
                self.successful_urls.add(url)

        if self.session:
            await self.session.close()

    async def __aenter__(self):
        await self._init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
