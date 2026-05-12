from __future__ import annotations

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
