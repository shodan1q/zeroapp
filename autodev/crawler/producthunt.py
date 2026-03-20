"""ProductHunt crawler -- discovers trending product ideas."""

from __future__ import annotations

from autodev.crawler.base import BaseCrawler, RawDemand


class ProductHuntCrawler(BaseCrawler):
    """Crawl ProductHunt for trending products and gaps. (Stub)"""

    async def crawl(self, limit: int = 50) -> list[RawDemand]:
        """Fetch trending products from ProductHunt.

        TODO: Implement using ProductHunt GraphQL API.
        """
        raise NotImplementedError("ProductHunt crawler not yet implemented")

    def source_name(self) -> str:
        return "producthunt"
