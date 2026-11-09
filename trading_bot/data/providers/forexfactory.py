"""ForexFactory economic calendar provider with mandatory blackout fail-safe."""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from trading_bot.core.logger import get_logger
from trading_bot.data.providers.calendar_interface import (
    CalendarEvent,
    CalendarImpact,
    CalendarProviderInterface,
)

logger = get_logger("providers.forexfactory")


class ForexFactoryCalendarProvider(CalendarProviderInterface):
    """ForexFactory economic calendar feed parser.
    
    CRITICAL INVARIANT: If the calendar feed is unavailable, timed out, or stale,
    all currencies are treated as in a mandatory blackout state to prevent trading
    blindly into surprise high-impact macroeconomic releases.
    """

    FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def __init__(
        self,
        feed_url: str | None = None,
        max_feed_age_hours: float = 6.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.feed_url = feed_url or self.FEED_URL
        self.max_feed_age = timedelta(hours=max_feed_age_hours)
        self._http_client = http_client
        self._cached_events: list[CalendarEvent] = []
        self._last_successful_fetch: datetime | None = None
        self._is_stale_or_unavailable: bool = False

    @property
    def provider_name(self) -> str:
        return "forexfactory"

    @property
    def is_stale_or_unavailable(self) -> bool:
        """True if the feed has never succeeded, failed recently, or cache is expired."""
        if not self._cached_events or self._last_successful_fetch is None:
            return True
        age = datetime.now(timezone.utc) - self._last_successful_fetch
        return age > self.max_feed_age or self._is_stale_or_unavailable

    async def fetch_events(self) -> list[CalendarEvent]:
        """Fetch economic calendar events from ForexFactory JSON feed."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(self.feed_url)
                resp.raise_for_status()
                raw_events = resp.json()

            parsed_events: list[CalendarEvent] = []
            for item in raw_events:
                event = self._parse_event_dict(item)
                if event is not None:
                    parsed_events.append(event)

            self._cached_events = parsed_events
            self._last_successful_fetch = datetime.now(timezone.utc)
            self._is_stale_or_unavailable = False
            logger.info("Successfully fetched %d ForexFactory calendar events.", len(parsed_events))
            return self._cached_events
        except Exception as err:
            self._is_stale_or_unavailable = True
            logger.error(
                "CALENDAR_FEED_UNAVAILABLE: Failed to fetch ForexFactory events: %s. "
                "Engaging mandatory calendar blackout for all currencies.",
                err,
            )
            # Retain cached events if available, but flag as unavailable/stale
            return self._cached_events

    def is_currency_in_blackout(
        self,
        currency: str,
        check_time: datetime | None = None,
        blackout_before_minutes: int = 30,
        blackout_after_minutes: int = 30,
    ) -> tuple[bool, str | None]:
        """Determine if currency is blacked out due to high-impact events or feed failure.
        
        Returns:
            (is_blackout, reason)
        """
        now = check_time or datetime.now(timezone.utc)
        now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)

        # Non-negotiable: If calendar feed is unavailable or stale, treat as blackout!
        if self.is_stale_or_unavailable or not self._cached_events:
            return (
                True,
                f"CALENDAR_FEED_UNAVAILABLE_OR_STALE: Economic calendar offline for {currency}. "
                "All new entries blocked for safety.",
            )

        # Weekly rollover: If all events in current feed are in the past, rollover is occurring
        latest_event_time = max(e.timestamp for e in self._cached_events)
        if latest_event_time.tzinfo is None:
            latest_event_time = latest_event_time.replace(tzinfo=timezone.utc)
        if latest_event_time < now - timedelta(hours=2):
            return (
                True,
                f"CALENDAR_ROLLOVER_BLACKOUT: Weekly calendar feed ended for {currency}. "
                "Waiting for next week rollover feed.",
            )

        before_delta = timedelta(minutes=blackout_before_minutes)
        after_delta = timedelta(minutes=blackout_after_minutes)

        curr_upper = currency.upper().strip()

        for event in self._cached_events:
            if event.currency.upper() == curr_upper and event.impact == CalendarImpact.HIGH:
                event_ts = event.timestamp
                if event_ts.tzinfo is None:
                    event_ts = event_ts.replace(tzinfo=timezone.utc)
                else:
                    event_ts = event_ts.astimezone(timezone.utc)

                blackout_start = event_ts - before_delta
                blackout_end = event_ts + after_delta

                if blackout_start <= now <= blackout_end:
                    mins_diff = (event_ts - now).total_seconds() / 60.0
                    timing = f"{mins_diff:.0f}m before" if mins_diff >= 0 else f"{abs(mins_diff):.0f}m after"
                    return (
                        True,
                        f"CALENDAR_BLACKOUT: High-impact event '{event.title}' on {curr_upper} ({timing})",
                    )

        return False, None

    def set_events_for_testing(self, events: list[CalendarEvent], is_stale: bool = False) -> None:
        """Helper to inject mocked events and state for deterministic tests."""
        self._cached_events = events
        self._last_successful_fetch = datetime.now(timezone.utc)
        self._is_stale_or_unavailable = is_stale

    @staticmethod
    def _parse_event_dict(item: dict[str, Any]) -> CalendarEvent | None:
        try:
            title = str(item.get("title", "")).strip()
            country = str(item.get("country", "")).strip().upper()
            date_str = str(item.get("date", "")).strip()
            impact_raw = str(item.get("impact", "")).strip().capitalize()

            if not title or not country or not date_str:
                return None

            impact_map = {
                "High": CalendarImpact.HIGH,
                "Medium": CalendarImpact.MEDIUM,
                "Low": CalendarImpact.LOW,
                "Holiday": CalendarImpact.HOLIDAY,
            }
            impact = impact_map.get(impact_raw, CalendarImpact.LOW)

            # ISO parsing (e.g. 2026-11-09T13:30:00-05:00)
            try:
                dt = datetime.fromisoformat(date_str)
            except ValueError:
                return None

            dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

            event_id = f"{country}_{dt.strftime('%Y%m%d%H%M')}_{title[:16]}"
            return CalendarEvent(
                id=event_id,
                title=title,
                currency=country,
                timestamp=dt,
                impact=impact,
                forecast=str(item.get("forecast", "")) or None,
                previous=str(item.get("previous", "")) or None,
            )
        except Exception:
            return None
