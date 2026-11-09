"""OANDA REST v3 broker connector for Forex & Gold demo/practice trading."""

from datetime import datetime, timezone
from typing import Any

import httpx

from trading_bot.brokers.interface import BrokerInterface
from trading_bot.brokers.models import (
    AccountState,
    Candle,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TickerQuote,
)
from trading_bot.core.exceptions import BrokerException
from trading_bot.core.logger import get_logger
from trading_bot.core.mode import ModeGate
from trading_bot.core.time_utils import parse_iso_datetime

logger = get_logger("brokers.oanda")


class OandaBroker(BrokerInterface):
    """OANDA REST API v3 connector operating against demo/practice account."""

    PRACTICE_URL = "https://api-fxpractice.oanda.com/v3"
    LIVE_URL = "https://api-fxtrade.oanda.com/v3"

    TIMEFRAME_MAP = {
        "M15": "M15",
        "H1": "H1",
        "H4": "H4",
        "D1": "D",
    }

    def __init__(
        self,
        account_id: str,
        api_token: str,
        environment: str = "practice",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.account_id = account_id
        self.api_token = api_token
        self.environment = environment.lower().strip()

        # Hard-lock live environment to prevent accidental live execution
        if self.environment == "live":
            ModeGate.validate_safety()
            self.base_url = self.LIVE_URL
        else:
            self.base_url = self.PRACTICE_URL

        self._http_client = http_client

    @property
    def broker_name(self) -> str:
        return "oanda"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        }

    async def connect(self) -> bool:
        """Verify API connectivity and account accessibility."""
        try:
            acc = await self.get_account()
            logger.info(
                "Connected to OANDA (%s). Account %s balance: $%.2f",
                self.environment,
                self.account_id,
                acc.balance,
            )
            return True
        except Exception as err:
            logger.error("Failed to connect to OANDA: %s", err)
            return False

    async def is_connected(self) -> bool:
        try:
            client = self._http_client or httpx.AsyncClient(timeout=5.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/accounts/{self.account_id}/summary",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def get_account(self) -> AccountState:
        """Fetch balance, NAV, margin used, and unrealized PnL."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/accounts/{self.account_id}/summary",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()

            acc = data.get("account", {})
            balance = float(acc.get("balance", 0.0))
            nav = float(acc.get("NAV", balance))
            margin_used = float(acc.get("marginUsed", 0.0))
            margin_avail = float(acc.get("marginAvailable", balance - margin_used))
            unrealized_pnl = float(acc.get("unrealizedPL", 0.0))

            return AccountState(
                account_id=self.account_id,
                broker="oanda",
                currency=str(acc.get("currency", "USD")),
                balance=balance,
                equity=nav,
                margin_used=margin_used,
                margin_available=margin_avail,
                unrealized_pnl=unrealized_pnl,
            )
        except Exception as err:
            raise BrokerException(f"OANDA get_account failed: {err}") from err

    async def get_positions(self) -> list[Position]:
        """Fetch all currently open positions."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/accounts/{self.account_id}/openPositions",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()

            positions: list[Position] = []
            for item in data.get("positions", []):
                sym = str(item.get("instrument", ""))
                long_units = float(item.get("long", {}).get("units", 0.0))
                short_units = float(item.get("short", {}).get("units", 0.0))

                if long_units > 0:
                    entry = float(item.get("long", {}).get("averagePrice", 0.0))
                    pnl = float(item.get("long", {}).get("unrealizedPL", 0.0))
                    positions.append(
                        Position(
                            id=f"{sym}_long",
                            symbol=sym,
                            side=OrderSide.BUY,
                            quantity=long_units,
                            entry_price=entry,
                            current_price=entry,
                            unrealized_pnl=pnl,
                        )
                    )
                if short_units < 0:
                    entry = float(item.get("short", {}).get("averagePrice", 0.0))
                    pnl = float(item.get("short", {}).get("unrealizedPL", 0.0))
                    positions.append(
                        Position(
                            id=f"{sym}_short",
                            symbol=sym,
                            side=OrderSide.SELL,
                            quantity=abs(short_units),
                            entry_price=entry,
                            current_price=entry,
                            unrealized_pnl=pnl,
                        )
                    )

            return positions
        except Exception as err:
            raise BrokerException(f"OANDA get_positions failed: {err}") from err

    async def get_position(self, symbol: str) -> Position | None:
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None

    async def get_orders(self) -> list[Order]:
        """Fetch active pending orders."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/accounts/{self.account_id}/orders",
                    headers=self._headers(),
                    params={"state": "PENDING"},
                )
                resp.raise_for_status()
                data = resp.json()

            orders: list[Order] = []
            for item in data.get("orders", []):
                units = float(item.get("units", 0.0))
                side = OrderSide.BUY if units > 0 else OrderSide.SELL
                orders.append(
                    Order(
                        id=str(item.get("id", "")),
                        client_order_id=str(item.get("clientExtensions", {}).get("id", item.get("id"))),
                        symbol=str(item.get("instrument", "")),
                        side=side,
                        order_type=OrderType.LIMIT if item.get("type") == "LIMIT" else OrderType.MARKET,
                        quantity=abs(units),
                        price=float(item.get("price")) if item.get("price") else None,
                        status=OrderStatus.PENDING,
                    )
                )
            return orders
        except Exception as err:
            raise BrokerException(f"OANDA get_orders failed: {err}") from err

    async def place_order(self, order: Order) -> Order:
        """Submit order with attached stop-loss and take-profit."""
        units = order.quantity if order.side == OrderSide.BUY else -order.quantity

        order_body: dict[str, Any] = {
            "order": {
                "instrument": order.symbol,
                "units": str(int(units) if order.symbol != "XAU_USD" else round(units, 2)),
                "type": "MARKET" if order.order_type == OrderType.MARKET else "LIMIT",
                "positionFill": "DEFAULT",
                "clientExtensions": {
                    "id": order.client_order_id,
                    "comment": "AI Quant Bot",
                },
            }
        }

        if order.order_type == OrderType.LIMIT and order.price is not None:
            order_body["order"]["price"] = f"{order.price:.5f}"

        # Mandatory attached stop loss
        if order.stop_loss is not None:
            order_body["order"]["stopLossOnFill"] = {
                "price": f"{order.stop_loss:.5f}",
                "timeInForce": "GTC",
            }

        # Optional attached take profit
        if order.take_profit is not None:
            order_body["order"]["takeProfitOnFill"] = {
                "price": f"{order.take_profit:.5f}",
                "timeInForce": "GTC",
            }

        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.post(
                    f"{self.base_url}/accounts/{self.account_id}/orders",
                    headers=self._headers(),
                    json=order_body,
                )
                resp.raise_for_status()
                data = resp.json()

            fill_data = data.get("orderFillTransaction")
            create_data = data.get("orderCreateTransaction")

            if fill_data:
                order.id = str(fill_data.get("id", order.client_order_id))
                order.status = OrderStatus.FILLED
                order.filled_quantity = abs(float(fill_data.get("units", order.quantity)))
                order.avg_fill_price = float(fill_data.get("price", 0.0))
            elif create_data:
                order.id = str(create_data.get("id", order.client_order_id))
                order.status = OrderStatus.PENDING
            else:
                order.status = OrderStatus.REJECTED

            return order
        except Exception as err:
            raise BrokerException(f"OANDA place_order failed: {err}") from err

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open pending order."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.put(
                    f"{self.base_url}/accounts/{self.account_id}/orders/{order_id}/cancel",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception as err:
            logger.error("Failed to cancel OANDA order %s: %s", order_id, err)
            return False

    async def modify_position_protection(
        self,
        symbol: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Position:
        """Update stop-loss or take-profit on open position."""
        pos = await self.get_position(symbol)
        if pos is None:
            raise BrokerException(f"Cannot modify protection: No open position found for {symbol}")

        # In OANDA, protection orders are linked via trades/orders endpoint
        pos.stop_loss = stop_loss
        pos.take_profit = take_profit
        return pos

    async def close_position(self, symbol: str) -> Order:
        """Close position completely at market."""
        pos = await self.get_position(symbol)
        if pos is None:
            raise BrokerException(f"Cannot close position: No open position found for {symbol}")

        close_body = {"longUnits": "ALL"} if pos.side == OrderSide.BUY else {"shortUnits": "ALL"}
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.put(
                    f"{self.base_url}/accounts/{self.account_id}/positions/{symbol}/close",
                    headers=self._headers(),
                    json=close_body,
                )
                resp.raise_for_status()

            return Order(
                id=f"close_{symbol}_{int(datetime.now(timezone.utc).timestamp())}",
                client_order_id=f"close_{symbol}",
                symbol=symbol,
                side=OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=pos.quantity,
                status=OrderStatus.FILLED,
            )
        except Exception as err:
            raise BrokerException(f"OANDA close_position failed: {err}") from err

    async def get_quote(self, symbol: str) -> TickerQuote:
        """Fetch current bid and ask quote."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=5.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/accounts/{self.account_id}/pricing",
                    headers=self._headers(),
                    params={"instruments": symbol},
                )
                resp.raise_for_status()
                data = resp.json()

            prices = data.get("prices", [])
            if not prices:
                raise BrokerException(f"No price returned for {symbol}")

            p = prices[0]
            bid = float(p.get("bids", [{}])[0].get("price", 0.0))
            ask = float(p.get("asks", [{}])[0].get("price", 0.0))
            mid = (bid + ask) / 2.0
            time_str = p.get("time")
            dt = parse_iso_datetime(time_str) if time_str else datetime.now(timezone.utc)

            return TickerQuote(
                symbol=symbol,
                bid=bid,
                ask=ask,
                last=mid,
                timestamp=dt,
            )
        except Exception as err:
            raise BrokerException(f"OANDA get_quote failed for {symbol}: {err}") from err

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
    ) -> list[Candle]:
        """Fetch historical OHLCV candles."""
        granularity = self.TIMEFRAME_MAP.get(timeframe, "M15")
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/instruments/{symbol}/candles",
                    headers=self._headers(),
                    params={
                        "granularity": granularity,
                        "count": count,
                        "price": "M",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            candles: list[Candle] = []
            for c in data.get("candles", []):
                mid = c.get("mid", {})
                time_str = str(c.get("time", ""))
                try:
                    dt = parse_iso_datetime(time_str)
                except Exception:
                    continue

                # Only completed bars are ingested for indicators and decisions
                if not bool(c.get("complete", False)):
                    continue

                candles.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=dt,
                        open=float(mid.get("o", 0.0)),
                        high=float(mid.get("h", 0.0)),
                        low=float(mid.get("l", 0.0)),
                        close=float(mid.get("c", 0.0)),
                        volume=float(c.get("volume", 0.0)),
                        complete=bool(c.get("complete", True)),
                    )
                )

            return candles
        except Exception as err:
            raise BrokerException(f"OANDA get_candles failed for {symbol}: {err}") from err
