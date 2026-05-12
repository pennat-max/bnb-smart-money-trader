from __future__ import annotations

import asyncio
import time

import httpx

from .config import Settings
from .models import MarketSnapshot


class BinanceFuturesClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.futures_base_url

    async def _get(self, path: str, params: dict[str, str | int] | None = None):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    async def ticker_price(self, symbol: str) -> float:
        payload = await self._get("/fapi/v1/ticker/price", {"symbol": symbol})
        return float(payload["price"])

    async def klines(self, symbol: str, interval: str = "1m", limit: int = 120) -> list[list[float]]:
        payload = await self._get(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        return [
            [
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
            ]
            for row in payload
        ]

    async def raw_klines(self, symbol: str, interval: str = "1m", limit: int = 500) -> list[dict]:
        payload = await self._get(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": max(120, min(limit, 1500))},
        )
        return self._format_klines(payload)

    async def raw_klines_for_days(self, symbol: str, interval: str = "15m", days: int = 7) -> list[dict]:
        interval_ms = interval_to_ms(interval)
        end_time = int(time.time() * 1000)
        start_time = end_time - days * 24 * 60 * 60 * 1000
        candles: list[dict] = []
        cursor = start_time

        while cursor < end_time:
            payload = await self._get(
                "/fapi/v1/klines",
                {
                    "symbol": symbol,
                    "interval": interval,
                    "limit": 1500,
                    "startTime": cursor,
                    "endTime": end_time,
                },
            )
            batch = self._format_klines(payload)
            if not batch:
                break
            candles.extend(batch)
            next_cursor = batch[-1]["close_time"] + 1
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            await asyncio.sleep(0.05)

        unique = {candle["open_time"]: candle for candle in candles}
        return [unique[key] for key in sorted(unique)]

    def _format_klines(self, payload: list) -> list[dict]:
        return [
            {
                "open_time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "close_time": int(row[6]),
            }
            for row in payload
        ]

    async def funding_rate(self, symbol: str) -> float:
        payload = await self._get("/fapi/v1/premiumIndex", {"symbol": symbol})
        return float(payload.get("lastFundingRate", 0))

    async def open_interest(self, symbol: str) -> float:
        payload = await self._get("/fapi/v1/openInterest", {"symbol": symbol})
        return float(payload.get("openInterest", 0))

    async def snapshot(self, symbol: str = "BNBUSDT") -> MarketSnapshot:
        price = await self.ticker_price(symbol)
        btc_price = await self.ticker_price("BTCUSDT")
        candles = await self.klines(symbol)
        funding_rate = await self.funding_rate(symbol)
        open_interest = await self.open_interest(symbol)
        return MarketSnapshot(
            symbol=symbol,
            price=price,
            btc_price=btc_price,
            funding_rate=funding_rate,
            open_interest=open_interest,
            candles=candles,
        )


def interval_to_ms(interval: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    unit = interval[-1]
    if unit not in units:
        raise ValueError(f"Unsupported interval: {interval}")
    return int(interval[:-1]) * units[unit]
