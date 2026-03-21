"""App store review crawler -- mines low-rated reviews for feature gaps."""

from __future__ import annotations

from zerodev.crawler.base import BaseCrawler, RawDemand


class AppStoreCrawler(BaseCrawler):
    """Crawl app store reviews for unmet needs and feature requests. (Stub)"""

    async def crawl(self, limit: int = 50) -> list[RawDemand]:
        """Fetch negative reviews from Google Play / App Store.

        TODO: Implement using google-play-scraper for Google Play
              and itunes-app-scraper for Apple App Store.
        """
        raise NotImplementedError("App store review crawler not yet implemented")

    def source_name(self) -> str:
        return "appstore"
