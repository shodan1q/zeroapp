"""Base crawler abstract class."""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class RawDemand:
    """Raw demand data extracted from a source before LLM processing."""

    title: str
    body: str
    source: str
    source_url: str
    upvotes: int = 0
    comments: int = 0
    timestamp: str = ""


class BaseCrawler(abc.ABC):
    """Abstract base for all demand crawlers."""

    @abc.abstractmethod
    async def crawl(self, limit: int = 50) -> list[RawDemand]:
        """Crawl the source and return raw demands.

        Args:
            limit: Maximum number of items to fetch.

        Returns:
            List of RawDemand objects.
        """
        ...

    @abc.abstractmethod
    def source_name(self) -> str:
        """Return the canonical source name (e.g. 'reddit')."""
        ...
