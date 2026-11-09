"""External news and economic calendar providers."""

from trading_bot.data.providers.calendar_interface import (
    CalendarEvent,
    CalendarImpact,
    CalendarProviderInterface,
)
from trading_bot.data.providers.cryptopanic import CryptoPanicNewsProvider
from trading_bot.data.providers.finnhub import FinnhubProvider
from trading_bot.data.providers.forexfactory import ForexFactoryCalendarProvider
from trading_bot.data.providers.news_interface import (
    NewsItem,
    NewsProviderInterface,
)

__all__ = [
    "CalendarEvent",
    "CalendarImpact",
    "CalendarProviderInterface",
    "NewsItem",
    "NewsProviderInterface",
    "ForexFactoryCalendarProvider",
    "CryptoPanicNewsProvider",
    "FinnhubProvider",
]
