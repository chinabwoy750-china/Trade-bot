"""CryptoPanic crypto news provider with item-level prompt-injection quarantine."""

from datetime import datetime, timezone
from typing import Any

import httpx

from trading_bot.core.logger import get_logger
from trading_bot.data.providers.news_interface import NewsItem, NewsProviderInterface
from trading_bot.decision.parser import quarantine_untrusted_items

logger = get_logger("providers.cryptopanic")


class CryptoPanicNewsProvider(NewsProviderInterface):
    """CryptoPanic developer news API with granular prompt injection quarantine.
    
    Offending headlines matching prompt-injection patterns are isolated and dropped with
    an INPUT_INTEGRITY_FAILURE log, allowing all clean headlines to continue into the cycle.
    """

    BASE_URL = "https://cryptopanic.com/api/developer/v2/posts/"

    def __init__(
        self,
        api_token: str | None = None,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_token = api_token or ""
        self.base_url = base_url or self.BASE_URL
        self._http_client = http_client

    @property
    def provider_name(self) -> str:
        return "cryptopanic"

    async def fetch_news(
        self,
        symbols_or_currencies: list[str] | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        """Fetch news posts from CryptoPanic and sanitize each headline individually."""
        params: dict[str, Any] = {
            "public": "true",
        }
        if self.api_token:
            params["auth_token"] = self.api_token

        if symbols_or_currencies:
            currencies = [c.replace("/USD", "").replace("_USD", "") for c in symbols_or_currencies]
            params["currencies"] = ",".join(currencies[:5])

        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()
                data = resp.json()

            raw_results = data.get("results", [])
            return self._process_raw_posts(raw_results, limit=limit)
        except Exception as err:
            logger.error("Failed to fetch CryptoPanic news: %s. Returning empty news list.", err)
            return []

    def _process_raw_posts(self, posts: list[dict[str, Any]], limit: int = 50) -> list[NewsItem]:
        """Parse raw posts, run item-level quarantine, and return clean NewsItem objects."""
        # 1. First pass item-level prompt injection quarantine
        clean_posts, quarantined = quarantine_untrusted_items(
            items=posts,
            text_extractor=lambda p: str(p.get("title", "")),
            source="cryptopanic_feed",
        )

        if quarantined:
            logger.warning(
                "INPUT_INTEGRITY_FAILURE: Quarantined %d hostile/injected headline(s). "
                "Cycle continuing with %d verified clean headline(s).",
                len(quarantined),
                len(clean_posts),
            )

        news_items: list[NewsItem] = []
        for post in clean_posts[:limit]:
            item = self._parse_single_post(post)
            if item is not None:
                news_items.append(item)

        return news_items

    @staticmethod
    def _parse_single_post(post: dict[str, Any]) -> NewsItem | None:
        try:
            post_id = str(post.get("id", ""))
            title = str(post.get("title", "")).strip()
            if not title:
                return None

            # Calculate sentiment from community votes if present
            votes = post.get("votes", {})
            pos = float(votes.get("positive", 0) + votes.get("liked", 0) + votes.get("bullish", 0))
            neg = float(votes.get("negative", 0) + votes.get("disliked", 0) + votes.get("bearish", 0))
            total_votes = pos + neg
            sentiment = (pos - neg) / total_votes if total_votes > 0 else 0.0

            # Currencies
            currencies = [str(c.get("code", "")).upper() for c in post.get("currencies", []) if isinstance(c, dict)]

            # Published at
            pub_str = str(post.get("published_at", ""))
            try:
                dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.now(timezone.utc)

            return NewsItem(
                id=post_id,
                title=title,
                source=str(post.get("domain", "cryptopanic")),
                url=str(post.get("url", "")),
                published_at=dt,
                currencies=currencies,
                sentiment_score=round(sentiment, 2),
                is_quarantined=False,
            )
        except Exception:
            return None
