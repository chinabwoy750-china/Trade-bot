"""Alpaca broker connector for Crypto Spot paper trading (Long-only)."""

from datetime import datetime, timedelta, timezone
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
from trading_bot.core.exceptions import BrokerException, RiskVetoException
from trading_bot.core.logger import get_logger
from trading_bot.core.mode import ModeGate

logger = get_logger("brokers.alpaca")


class AlpacaBroker(BrokerInterface):
    """Alpaca Paper Trading REST connector for Crypto Spot.
    
    INVARIANTS:
    1. Spot long-only: Short orders are strictly rejected before touching the API.
    2. Paper-only default: Live API URL blocked unless ModeGate verifies live permission.
    3. Startup symbol verification: Unsupported or unlisted symbols are skipped with a clear log.
    """

    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"
    CRYPTO_DATA_URL = "https://data.alpaca.markets/v1beta3/crypto/us"

    TIMEFRAME_MAP = {
        "M15": "15Min",
        "H1": "1Hour",
        "H4": "4Hour",
        "D1": "1Day",
    }

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str | None = None,
        data_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        raw_url = base_url or self.PAPER_URL
        self.data_url = data_url or self.CRYPTO_DATA_URL
        self._http_client = http_client

        # Mode safety gate check
        if "paper" not in raw_url.lower():
            ModeGate.validate_safety()
            self.base_url = raw_url
        else:
            self.base_url = self.PAPER_URL

        # Active verified symbol universe
        self.supported_symbols: set[str] = set()

    @property
    def broker_name(self) -> str:
        return "alpaca"

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
        }

    async def verify_symbols(self, configured_symbols: list[str]) -> set[str]:
        """Verify which configured crypto symbols are actively tradeable on Alpaca.
        
        Skips unsupported symbols and logs a clear audit line as required by spec.
        """
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/v2/assets",
                    headers=self._headers(),
                    params={"asset_class": "crypto", "status": "active"},
                )
                resp.raise_for_status()
                assets = resp.json()

            tradeable_symbols = {
                str(a.get("symbol", "")).upper() for a in assets if a.get("tradable", False)
            }

            active_supported: set[str] = set()
            for sym in configured_symbols:
                normalized = sym.upper().replace("-", "/")
                # Alpaca lists symbols like BTC/USD or BTCUSD
                clean_sym = normalized.replace("/", "")
                if normalized in tradeable_symbols or clean_sym in tradeable_symbols:
                    active_supported.add(sym)
                else:
                    logger.warning(
                        "Alpaca crypto symbol %s is UNSUPPORTED or inactive on exchange. "
                        "Skipping from trading universe.",
                        sym,
                    )

            self.supported_symbols = active_supported
            logger.info(
                "Alpaca symbol verification complete: %d of %d symbols supported.",
                len(active_supported),
                len(configured_symbols),
            )
            return self.supported_symbols
        except Exception as err:
            logger.error("Failed to verify Alpaca assets: %s. Defaulting to configured list.", err)
            self.supported_symbols = set(configured_symbols)
            return self.supported_symbols

    async def connect(self) -> bool:
        """Verify credentials and retrieve account balance."""
        try:
            acc = await self.get_account()
            logger.info("Connected to Alpaca Paper. Equity: $%.2f", acc.equity)
            return True
        except Exception as err:
            logger.error("Failed to connect to Alpaca: %s", err)
            return False

    async def is_connected(self) -> bool:
        try:
            client = self._http_client or httpx.AsyncClient(timeout=5.0)
            async with client:
                resp = await client.get(f"{self.base_url}/v2/account", headers=self._headers())
                return resp.status_code == 200
        except Exception:
            return False

    async def get_account(self) -> AccountState:
        """Fetch account equity, cash balance, and buying power."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(f"{self.base_url}/v2/account", headers=self._headers())
                resp.raise_for_status()
                data = resp.json()

            equity = float(data.get("equity", 0.0))
            cash = float(data.get("cash", 0.0))
            buying_power = float(data.get("buying_power", cash))

            return AccountState(
                account_id=str(data.get("id", "alpaca_paper")),
                broker="alpaca",
                currency=str(data.get("currency", "USD")),
                balance=cash,
                equity=equity,
                margin_available=buying_power,
            )
        except Exception as err:
            raise BrokerException(f"Alpaca get_account failed: {err}") from err

    async def get_positions(self) -> list[Position]:
        """Fetch all currently open crypto positions."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(f"{self.base_url}/v2/positions", headers=self._headers())
                resp.raise_for_status()
                data = resp.json()

            positions: list[Position] = []
            for item in data:
                sym = str(item.get("symbol", ""))
                # Normalize BTCUSD -> BTC/USD if needed
                display_sym = f"{sym[:-3]}/USD" if "/" not in sym and sym.endswith("USD") else sym

                qty = float(item.get("qty", 0.0))
                entry = float(item.get("avg_entry_price", 0.0))
                curr = float(item.get("current_price", entry))
                pnl = float(item.get("unrealized_pl", 0.0))
                side = OrderSide.BUY if item.get("side") == "long" else OrderSide.SELL

                positions.append(
                    Position(
                        id=f"{display_sym}_{item.get('asset_id', '')}",
                        symbol=display_sym,
                        side=side,
                        quantity=qty,
                        entry_price=entry,
                        current_price=curr,
                        unrealized_pnl=pnl,
                    )
                )
            return positions
        except Exception as err:
            raise BrokerException(f"Alpaca get_positions failed: {err}") from err

    async def get_position(self, symbol: str) -> Position | None:
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol or pos.symbol.replace("/", "") == symbol.replace("/", ""):
                return pos
        return None

    async def get_orders(self) -> list[Order]:
        """Fetch active open orders."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(
                    f"{self.base_url}/v2/orders",
                    headers=self._headers(),
                    params={"status": "open"},
                )
                resp.raise_for_status()
                data = resp.json()

            orders: list[Order] = []
            for item in data:
                sym = str(item.get("symbol", ""))
                side = OrderSide.BUY if item.get("side") == "buy" else OrderSide.SELL
                orders.append(
                    Order(
                        id=str(item.get("id", "")),
                        client_order_id=str(item.get("client_order_id", item.get("id"))),
                        symbol=sym,
                        side=side,
                        order_type=OrderType.LIMIT if item.get("type") == "limit" else OrderType.MARKET,
                        quantity=float(item.get("qty", 0.0)),
                        price=float(item.get("limit_price")) if item.get("limit_price") else None,
                        status=OrderStatus.PENDING,
                    )
                )
            return orders
        except Exception as err:
            raise BrokerException(f"Alpaca get_orders failed: {err}") from err

    async def place_order(self, order: Order) -> Order:
        """Place paper order. Rejects short selling (spot long-only rule)."""
        # NON-NEGOTIABLE PRINCIPLE: Crypto is spot long-only
        if order.side == OrderSide.SELL:
            existing = await self.get_position(order.symbol)
            if existing is None or existing.quantity < order.quantity:
                raise RiskVetoException(
                    rule_name="CRYPTO_SPOT_LONG_ONLY",
                    message=f"Short selling {order.symbol} is forbidden on spot crypto.",
                )

        order_body: dict[str, Any] = {
            "symbol": order.symbol.replace("/", ""),
            "qty": str(order.quantity),
            "side": "buy" if order.side == OrderSide.BUY else "sell",
            "type": "market" if order.order_type == OrderType.MARKET else "limit",
            "time_in_force": "gtc",
            "client_order_id": order.client_order_id,
        }

        if order.order_type == OrderType.LIMIT and order.price is not None:
            order_body["limit_price"] = str(order.price)

        # In Alpaca, stop loss can be attached via bracket/oto class for crypto limit orders
        if order.stop_loss is not None:
            order_body["stop_loss"] = {"stop_price": str(order.stop_loss)}

        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.post(
                    f"{self.base_url}/v2/orders",
                    headers=self._headers(),
                    json=order_body,
                )
                resp.raise_for_status()
                data = resp.json()

            order.id = str(data.get("id", order.client_order_id))
            status_raw = str(data.get("status", "pending")).lower()
            if status_raw in ("filled", "partially_filled"):
                order.status = OrderStatus.FILLED
                order.filled_quantity = float(data.get("filled_qty", order.quantity))
                order.avg_fill_price = float(data.get("filled_avg_price", 0.0))
            else:
                order.status = OrderStatus.PENDING

            return order
        except Exception as err:
            raise BrokerException(f"Alpaca place_order failed: {err}") from err

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by ID."""
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.delete(
                    f"{self.base_url}/v2/orders/{order_id}",
                    headers=self._headers(),
                )
                return resp.status_code in (200, 204)
        except Exception as err:
            logger.error("Failed to cancel Alpaca order %s: %s", order_id, err)
            return False

    async def modify_position_protection(
        self,
        symbol: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Position:
        pos = await self.get_position(symbol)
        if pos is None:
            raise BrokerException(f"No open position found on Alpaca for {symbol}")
        pos.stop_loss = stop_loss
        pos.take_profit = take_profit
        return pos

    async def close_position(self, symbol: str) -> Order:
        """Close an open crypto position completely."""
        clean_sym = symbol.replace("/", "")
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.delete(
                    f"{self.base_url}/v2/positions/{clean_sym}",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()

            return Order(
                id=str(data.get("id", f"close_{clean_sym}")),
                client_order_id=f"close_{clean_sym}",
                symbol=symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=float(data.get("qty", 0.0)),
                status=OrderStatus.FILLED,
            )
        except Exception as err:
            raise BrokerException(f"Alpaca close_position failed for {symbol}: {err}") from err

    async def get_quote(self, symbol: str) -> TickerQuote:
        """Fetch latest crypto quote from Alpaca Crypto Data API."""
        norm_sym = symbol.replace("-", "/").upper()
        try:
            client = self._http_client or httpx.AsyncClient(timeout=5.0)
            async with client:
                resp = await client.get(
                    f"{self.data_url}/latest/quotes",
                    headers=self._headers(),
                    params={"symbols": norm_sym},
                )
                resp.raise_for_status()
                data = resp.json()

            quotes = data.get("quotes", {})
            q = quotes.get(norm_sym) or quotes.get(norm_sym.replace("/", ""))
            if not q:
                raise BrokerException(f"No quote returned for crypto symbol {norm_sym}")

            bid = float(q.get("bp", 0.0))
            ask = float(q.get("ap", 0.0))
            mid = (bid + ask) / 2.0
            time_str = q.get("t")
            dt = (
                datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                if time_str
                else datetime.now(timezone.utc)
            )

            return TickerQuote(
                symbol=symbol,
                bid=bid,
                ask=ask,
                last=mid,
                timestamp=dt,
            )
        except Exception as err:
            raise BrokerException(f"Alpaca get_quote failed for {symbol}: {err}") from err

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
    ) -> list[Candle]:
        """Fetch crypto OHLCV bars from Alpaca Data API."""
        tf = self.TIMEFRAME_MAP.get(timeframe, "15Min")
        norm_sym = symbol.replace("-", "/").upper()

        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            async with client:
                resp = await client.get(
                    f"{self.data_url}/bars",
                    headers=self._headers(),
                    params={
                        "symbols": norm_sym,
                        "timeframe": tf,
                        "limit": count,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            bars_data = data.get("bars", {})
            if isinstance(bars_data, dict):
                bars = bars_data.get(norm_sym, [])
            elif isinstance(bars_data, list):
                bars = bars_data
            else:
                bars = []

            # Determine bar interval duration
            tf_delta = {
                "M15": timedelta(minutes=15),
                "H1": timedelta(hours=1),
                "H4": timedelta(hours=4),
                "D1": timedelta(days=1),
            }.get(timeframe.upper(), timedelta(minutes=15))

            now_utc = datetime.now(timezone.utc)
            candles: list[Candle] = []
            for b in bars:
                time_str = str(b.get("t", ""))
                try:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
                except ValueError:
                    continue

                # Drop forming bar: if bar close time is in the future, it is incomplete!
                if dt + tf_delta > now_utc:
                    logger.debug("Dropping forming Alpaca candle at %s for %s", dt.isoformat(), symbol)
                    continue

                candles.append(
                    Candle(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=dt,
                        open=float(b.get("o", 0.0)),
                        high=float(b.get("h", 0.0)),
                        low=float(b.get("l", 0.0)),
                        close=float(b.get("c", 0.0)),
                        volume=float(b.get("v", 0.0)),
                        complete=True,
                    )
                )

            return candles
        except Exception as err:
            raise BrokerException(f"Alpaca get_candles failed for {symbol}: {err}") from err
