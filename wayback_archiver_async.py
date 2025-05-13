import asyncio
import aiohttp
from typing import Set, List, Optional
import logging
from wayback_archiver import WaybackArchiver

class AsyncWaybackArchiver(WaybackArchiver):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_concurrent = kwargs.get('max_concurrent', 3)
        self.session = None

    async def _init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def _archive_url_async(self, url: str) -> bool:
        try:
            async with self.session.post(
                "https://web.archive.org/save",
                params=self._get_archive_params(url),
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                return response.status in [200, 201]
        except Exception as e:
            logger.error(f"Error archiving {url}: {str(e)}")
            return False

    async def archive_urls_async(self):
        """Archive URLs concurrently with rate limiting."""
        await self._init_session()
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def archive_with_semaphore(url: str) -> bool:
            async with semaphore:
                await asyncio.sleep(self.delay)  # Rate limiting
                return await self._archive_url_async(url)

        tasks = [archive_with_semaphore(url) for url in self.urls_to_archive]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for url, result in zip(self.urls_to_archive, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to archive {url}: {str(result)}")
            elif result:
                self.successful_urls.add(url)

        if self.session:
            await self.session.close()
