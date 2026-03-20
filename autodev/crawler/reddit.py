"""Reddit crawler -- scrapes subreddits like r/AppIdeas for app demands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from autodev.crawler.base import BaseCrawler, RawDemand

if TYPE_CHECKING:
    import praw


SUBREDDITS = [
    "AppIdeas",
    "SomebodyMakeThis",
    "AppBusiness",
    "androidapps",
    "iOSProgramming",
]


class RedditCrawler(BaseCrawler):
    """Crawl Reddit for app ideas and feature requests."""

    def __init__(self, client_id: str, client_secret: str, user_agent: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._user_agent = user_agent
        self._reddit: praw.Reddit | None = None

    def _get_reddit(self) -> praw.Reddit:
        if self._reddit is None:
            import praw as _praw

            self._reddit = _praw.Reddit(
                client_id=self._client_id,
                client_secret=self._client_secret,
                user_agent=self._user_agent,
            )
        return self._reddit

    async def crawl(self, limit: int = 50) -> list[RawDemand]:
        """Fetch hot posts from target subreddits."""
        reddit = self._get_reddit()
        demands: list[RawDemand] = []

        for sub_name in SUBREDDITS:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.hot(limit=limit):
                if post.stickied:
                    continue
                demands.append(
                    RawDemand(
                        title=post.title,
                        body=post.selftext or "",
                        source="reddit",
                        source_url=f"https://reddit.com{post.permalink}",
                        upvotes=post.score,
                        comments=post.num_comments,
                        timestamp=str(post.created_utc),
                    )
                )
        return demands

    def source_name(self) -> str:
        return "reddit"
