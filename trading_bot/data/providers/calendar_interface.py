"""Abstract interface and domain models for economic calendar data."""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class CalendarImpact(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    HOLIDAY = "HOLIDAY"


class CalendarEvent(BaseModel):
    """Economic calendar scheduled event."""
    id: str
    title: str
    currency: str  # e.g., "USD", "EUR", "GBP", "JPY"
    timestamp: datetime
    impact: CalendarImpact
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


class CalendarProviderInterface(ABC):
    """Abstract interface for economic calendar feeds."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier name of the calendar provider."""
        pass

    @abstractmethod
    async def fetch_events(self) -> list[CalendarEvent]:
        """Fetch latest scheduled economic events."""
        pass

    @abstractmethod
    def is_currency_in_blackout(
        self,
        currency: str,
        check_time: datetime | None = None,
        blackout_before_minutes: int = 30,
        blackout_after_minutes: int = 30,
    ) -> tuple[bool, str | None]:
        """Check if a currency is within a blackout window around high-impact events.
        
        Returns:
            (is_blackout: bool, reason_or_event_title: str | None)
        """
        pass
