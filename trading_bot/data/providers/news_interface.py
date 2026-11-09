"""Abstract interface and domain models for financial news data."""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """Normalized financial news article or headline."""
    id: str
    title: str
    source: str
    url: str | None = None
    published_at: datetime
    currencies: list[str] = Field(default_factory=list)  # e.g., ["USD", "EUR"] or ["BTC", "ETH"]
    sentiment_score: float = 0.0  # -1.0 (bearish) to +1.0 (bullish)
    is_quarantined: bool = False


class NewsProviderInterface(ABC):
    """Abstract interface for financial news providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier name of the news provider."""
        pass

    @abstractmethod
    async def fetch_news(
        self,
        symbols_or_currencies: list[str] | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        """Fetch and return sanitized news items."""
        pass
