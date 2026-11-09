"""Finnhub provider implementing both Calendar and News interfaces as a swappable fallback."""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from trading_bot.core.logger import get_logger
from trading_bot.data.providers.calendar_interface import (
    CalendarEvent,
    CalendarImpact,
    CalendarProviderInterface,
)
from trading_bot.data.providers.news_interface import NewsItem, NewsProviderInterface
from trading_bot.decision.parser import quarantine_untrusted_items

logger = get_logger("providers.finnhub")


class FinnhubProvider(CalendarProviderInterface, NewsProviderInterface):
    """Fallback economic calendar and news provider using Finnhub REST API."""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or ""
        self.base_url = base_url or self.BASE_URL
        self._http_client = http_client
        self._cached_events: list[CalendarEvent] = []
        self._last_calendar_fetch: datetime | None = None
        self._is_stale_or_unavailable: bool = False

    @property
    def provider_name(self) -> str:
        return "finnhub"

    @property
    def is_stale_or_unavailable(self) -> bool:
        if not self._cached_events or self._last_calendar_fetch is None:
            return True
        age = datetime.now(timezone.utc) - self._last_calendar_fetch
        return age > timedelta(hours=6.0) or self._is_stale_or_unavailable

    async def fetch_events(self) -> list[CalendarEvent]:
        """Fetch economic calendar events from Finnhub."""
        if not self.api_key:
            self._is_stale_or_unavailable = True
            return []

        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/calendar/economic",
                    params={"token": self.api_key},
                )
                resp.raise_for_status()
                data = resp.json()

            raw_events = data.get("economicCalendar", [])
            events: list[CalendarEvent] = []
            for item in raw_events:
                ev = self._parse_event(item)
                if ev is not None:
                    events.append(ev)

            self._cached_events = events
            self._last_calendar_fetch = datetime.now(timezone.utc)
            self._is_stale_or_unavailable = False
            return events
        except Exception as err:
            self._is_stale_or_unavailable = True
            logger.error("Failed to fetch Finnhub calendar: %s", err)
            return self._cached_events

    def is_currency_in_blackout(
        self,
        currency: str,
        check_time: datetime | None = None,
        blackout_before_minutes: int = 30,
        blackout_after_minutes: int = 30,
    ) -> tuple[bool, str | None]:
        if self.is_stale_or_unavailable:
            return True, f"CALENDAR_FEED_UNAVAILABLE_OR_STALE: Finnhub calendar offline for {currency}."

        now = check_time or datetime.now(timezone.utc)
        curr_upper = currency.upper().strip()
        before_delta = timedelta(minutes=blackout_before_minutes)
        after_delta = timedelta(minutes=blackout_after_minutes)

        for event in self._cached_events:
            if event.currency.upper() == curr_upper and event.impact == CalendarImpact.HIGH:
                event_ts = event.timestamp
                if event_ts.tzinfo is None:
                    event_ts = event_ts.replace(tzinfo=timezone.utc)
                if (event_ts - before_delta) <= now <= (event_ts + after_delta):
                    return True, f"CALENDAR_BLACKOUT: {event.title} on {curr_upper}"

        return False, None

    async def fetch_news(
        self,
        symbols_or_currencies: list[str] | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        """Fetch general and market news from Finnhub."""
        if not self.api_key:
            return []

        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/news",
                    params={"category": "forex", "token": self.api_key},
                )
                resp.raise_for_status()
                raw_articles = resp.json()

            # Item-level prompt injection quarantine
            clean_articles, quarantined = quarantine_untrusted_items(
                items=raw_articles,
                text_extractor=lambda a: str(a.get("headline", "")),
                source="finnhub_news",
            )

            news: list[NewsItem] = []
            for art in clean_articles[:limit]:
                title = str(art.get("headline", "")).strip()
                if not title:
                    continue
                dt_ts = art.get("datetime")
                dt = (
                    datetime.fromtimestamp(dt_ts, tz=timezone.utc)
                    if dt_ts
                    else datetime.now(timezone.utc)
                )
                news.append(
                    NewsItem(
                        id=str(art.get("id", "")),
                        title=title,
                        source=str(art.get("source", "finnhub")),
                        url=str(art.get("url", "")),
                        published_at=dt,
                        sentiment_score=0.0,
                    )
                )
            return news
        except Exception as err:
            logger.error("Failed to fetch Finnhub news: %s", err)
            return []

    @staticmethod
    def _parse_event(item: dict[str, Any]) -> CalendarEvent | None:
        try:
            event_title = str(item.get("event", "")).strip()
            currency = str(item.get("currency", "")).strip().upper()
            time_str = str(item.get("time", "")).strip()
            impact_raw = str(item.get("impact", "")).strip().lower()

            if not event_title or not currency or not time_str:
                return None

            impact_map = {
                "3": CalendarImpact.HIGH,
                "high": CalendarImpact.HIGH,
                "2": CalendarImpact.MEDIUM,
                "medium": CalendarImpact.MEDIUM,
                "1": CalendarImpact.LOW,
                "low": CalendarImpact.LOW,
            }
            impact = impact_map.get(impact_raw, CalendarImpact.LOW)

            try:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            except ValueError:
                return None

            return CalendarEvent(
                id=f"{currency}_{event_title[:10]}",
                title=event_title,
                currency=currency,
                timestamp=dt,
                impact=impact,
                actual=str(item.get("actual", "")) or None,
                forecast=str(item.get("estimate", "")) or None,
                previous=str(item.get("prev", "")) or None,
            )
        except Exception:
            return None
