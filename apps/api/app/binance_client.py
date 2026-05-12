from __future__ import annotations

import asyncio
import time
from statistics import fmean, pstdev

import httpx

from .config import Settings
from .models import MarketSnapshot


class BinanceFuturesClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.futures_base_url
        self.market_data_url = "https://fapi.binance.com"

    async def _get(self, path: str, params: dict[str, str | int] | None = None):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    async def _get_market_data(self, path: str, params: dict[str, str | int] | None = None):
        async with httpx.AsyncClient(base_url=self.market_data_url, timeout=10) as client:
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

    async def open_interest_hist(self, symbol: str, period: str = "15m", limit: int = 30) -> list[dict]:
        payload = await self._get_market_data(
            "/futures/data/openInterestHist",
            {"symbol": symbol, "period": market_data_period(period), "limit": max(2, min(limit, 500))},
        )
        return [
            {
                "timestamp": int(row["timestamp"]),
                "sum_open_interest": float(row.get("sumOpenInterest", 0)),
                "sum_open_interest_value": float(row.get("sumOpenInterestValue", 0)),
            }
            for row in payload
        ]

    async def global_long_short_ratio(self, symbol: str, period: str = "15m", limit: int = 30) -> list[dict]:
        payload = await self._get_market_data(
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol, "period": market_data_period(period), "limit": max(1, min(limit, 500))},
        )
        return [
            {
                "timestamp": int(row["timestamp"]),
                "long_short_ratio": float(row.get("longShortRatio", 1)),
                "long_account": float(row.get("longAccount", 0.5)),
                "short_account": float(row.get("shortAccount", 0.5)),
            }
            for row in payload
        ]

    async def taker_buy_sell_volume(self, symbol: str, period: str = "15m", limit: int = 30) -> list[dict]:
        payload = await self._get_market_data(
            "/futures/data/takerlongshortRatio",
            {"symbol": symbol, "period": market_data_period(period), "limit": max(1, min(limit, 500))},
        )
        return [
            {
                "timestamp": int(row["timestamp"]),
                "buy_sell_ratio": float(row.get("buySellRatio", 1)),
                "buy_volume": float(row.get("buyVol", 0)),
                "sell_volume": float(row.get("sellVol", 0)),
            }
            for row in payload
        ]

    async def order_book_snapshot(self, symbol: str, limit: int = 50) -> dict:
        payload = await self._get_market_data("/fapi/v1/depth", {"symbol": symbol, "limit": max(5, min(limit, 100))})
        bids = [(float(row[0]), float(row[1])) for row in payload.get("bids", [])]
        asks = [(float(row[0]), float(row[1])) for row in payload.get("asks", [])]
        bid_qty = sum(row[1] for row in bids)
        ask_qty = sum(row[1] for row in asks)
        total_qty = bid_qty + ask_qty
        strongest_bid = max(bids, key=lambda row: row[1], default=(0, 0))
        strongest_ask = max(asks, key=lambda row: row[1], default=(0, 0))
        wall_side = "neutral"
        wall_price = None
        if strongest_bid[1] > strongest_ask[1] * 1.35:
            wall_side = "bid"
            wall_price = strongest_bid[0]
        elif strongest_ask[1] > strongest_bid[1] * 1.35:
            wall_side = "ask"
            wall_price = strongest_ask[0]
        return {
            "bid_ask_imbalance": ((bid_qty - ask_qty) / total_qty) if total_qty else 0,
            "depth_bid_qty": bid_qty,
            "depth_ask_qty": ask_qty,
            "depth_wall_side": wall_side,
            "depth_wall_price": wall_price,
        }

    async def recent_liquidations(self, symbol: str, limit: int = 100) -> dict:
        context = {
            "liquidation_buy_qty": 0,
            "liquidation_sell_qty": 0,
            "liquidation_imbalance": 0,
            "liquidation_spike": False,
        }
        try:
            payload = await self._get_market_data(
                "/fapi/v1/allForceOrders",
                {"symbol": symbol, "limit": max(10, min(limit, 100))},
            )
        except Exception:
            return context

        buy_qty = 0.0
        sell_qty = 0.0
        for row in payload:
            qty = float(row.get("origQty", row.get("executedQty", 0)) or 0)
            if row.get("side") == "BUY":
                buy_qty += qty
            elif row.get("side") == "SELL":
                sell_qty += qty
        total = buy_qty + sell_qty
        context["liquidation_buy_qty"] = buy_qty
        context["liquidation_sell_qty"] = sell_qty
        context["liquidation_imbalance"] = ((buy_qty - sell_qty) / total) if total else 0
        context["liquidation_spike"] = total > 50
        return context

    def candle_context(self, candles: list[list[float]]) -> dict:
        if not candles:
            return {
                "vwap": 0,
                "session_high": 0,
                "session_low": 0,
                "session_position": 0.5,
                "volume_zscore": 0,
            }
        typical_volume = [((row[1] + row[2] + row[3]) / 3, row[4]) for row in candles]
        total_volume = sum(volume for _, volume in typical_volume)
        vwap = sum(price * volume for price, volume in typical_volume) / total_volume if total_volume else candles[-1][3]
        session_high = max(row[1] for row in candles)
        session_low = min(row[2] for row in candles)
        session_range = max(session_high - session_low, 0.0001)
        volumes = [row[4] for row in candles]
        volume_sigma = pstdev(volumes) if len(volumes) > 1 else 0
        volume_zscore = ((volumes[-1] - fmean(volumes)) / volume_sigma) if volume_sigma else 0
        return {
            "vwap": vwap,
            "session_high": session_high,
            "session_low": session_low,
            "session_position": (candles[-1][3] - session_low) / session_range,
            "volume_zscore": volume_zscore,
        }

    async def multi_timeframe_context(self, symbol: str) -> dict:
        trends: dict[str, str] = {}
        score = 0
        for interval in ("5m", "15m", "1h"):
            try:
                candles = await self.klines(symbol, interval=interval, limit=80)
                trend = trend_from_candles(candles)
            except Exception:
                trend = "mixed"
            trends[interval] = trend
            if trend == "bullish":
                score += 1
            elif trend == "bearish":
                score -= 1
        bias = "bullish" if score >= 2 else "bearish" if score <= -2 else "mixed"
        return {"mtf_trends": trends, "mtf_alignment_score": score, "mtf_bias": bias}

    async def derivatives_context(self, symbol: str, period: str = "15m", limit: int = 30) -> dict:
        context = {
            "data_ok": False,
            "open_interest_change_pct": 0,
            "long_short_ratio": 1,
            "long_account": 0.5,
            "short_account": 0.5,
            "taker_buy_sell_ratio": 1,
            "taker_buy_volume_ratio": 0.5,
            "bid_ask_imbalance": 0,
            "depth_bid_qty": 0,
            "depth_ask_qty": 0,
            "depth_wall_side": "neutral",
            "depth_wall_price": None,
            "liquidation_buy_qty": 0,
            "liquidation_sell_qty": 0,
            "liquidation_imbalance": 0,
            "liquidation_spike": False,
        }
        try:
            oi_rows = await self.open_interest_hist(symbol, period=period, limit=limit)
            if len(oi_rows) >= 2 and oi_rows[-2]["sum_open_interest"]:
                context["open_interest_change_pct"] = (
                    (oi_rows[-1]["sum_open_interest"] - oi_rows[-2]["sum_open_interest"])
                    / oi_rows[-2]["sum_open_interest"]
                ) * 100
                context["data_ok"] = True
        except Exception:
            pass

        try:
            ratio_rows = await self.global_long_short_ratio(symbol, period=period, limit=limit)
            if ratio_rows:
                context["long_short_ratio"] = ratio_rows[-1]["long_short_ratio"]
                context["long_account"] = ratio_rows[-1]["long_account"]
                context["short_account"] = ratio_rows[-1]["short_account"]
                context["data_ok"] = True
        except Exception:
            pass

        try:
            taker_rows = await self.taker_buy_sell_volume(symbol, period=period, limit=limit)
            if taker_rows:
                latest = taker_rows[-1]
                total_volume = latest["buy_volume"] + latest["sell_volume"]
                context["taker_buy_sell_ratio"] = latest["buy_sell_ratio"]
                context["taker_buy_volume_ratio"] = latest["buy_volume"] / total_volume if total_volume else 0.5
                context["data_ok"] = True
        except Exception:
            pass

        try:
            context.update(await self.order_book_snapshot(symbol))
            context["data_ok"] = True
        except Exception:
            pass

        context.update(await self.recent_liquidations(symbol))

        return context

    async def derivatives_history(self, symbol: str, period: str = "15m", limit: int = 500) -> list[dict]:
        rows: dict[int, dict] = {}

        try:
            oi_rows = await self.open_interest_hist(symbol, period=period, limit=limit)
            for index, row in enumerate(oi_rows):
                previous = oi_rows[index - 1]["sum_open_interest"] if index > 0 else row["sum_open_interest"]
                rows.setdefault(row["timestamp"], {})["open_interest_change_pct"] = (
                    ((row["sum_open_interest"] - previous) / previous) * 100 if previous else 0
                )
        except Exception:
            pass

        try:
            ratio_rows = await self.global_long_short_ratio(symbol, period=period, limit=limit)
            for row in ratio_rows:
                rows.setdefault(row["timestamp"], {})["long_short_ratio"] = row["long_short_ratio"]
        except Exception:
            pass

        try:
            taker_rows = await self.taker_buy_sell_volume(symbol, period=period, limit=limit)
            for row in taker_rows:
                total_volume = row["buy_volume"] + row["sell_volume"]
                rows.setdefault(row["timestamp"], {})["taker_buy_sell_ratio"] = row["buy_sell_ratio"]
                rows.setdefault(row["timestamp"], {})["taker_buy_volume_ratio"] = (
                    row["buy_volume"] / total_volume if total_volume else 0.5
                )
        except Exception:
            pass

        return [
            {
                "timestamp": timestamp,
                "open_interest_change_pct": values.get("open_interest_change_pct", 0),
                "long_short_ratio": values.get("long_short_ratio", 1),
                "taker_buy_sell_ratio": values.get("taker_buy_sell_ratio", 1),
                "taker_buy_volume_ratio": values.get("taker_buy_volume_ratio", 0.5),
            }
            for timestamp, values in sorted(rows.items())
        ]

    async def snapshot(self, symbol: str = "BNBUSDT") -> MarketSnapshot:
        price = await self.ticker_price(symbol)
        btc_price = await self.ticker_price("BTCUSDT")
        candles = await self.klines(symbol)
        funding_rate = await self.funding_rate(symbol)
        open_interest = await self.open_interest(symbol)
        derivatives = await self.derivatives_context(symbol, period="15m", limit=30)
        candle_context = self.candle_context(candles)
        mtf_context = await self.multi_timeframe_context(symbol)
        return MarketSnapshot(
            symbol=symbol,
            price=price,
            btc_price=btc_price,
            funding_rate=funding_rate,
            open_interest=open_interest,
            open_interest_change_pct=derivatives["open_interest_change_pct"],
            long_short_ratio=derivatives["long_short_ratio"],
            taker_buy_sell_ratio=derivatives["taker_buy_sell_ratio"],
            taker_buy_volume_ratio=derivatives["taker_buy_volume_ratio"],
            bid_ask_imbalance=derivatives["bid_ask_imbalance"],
            depth_bid_qty=derivatives["depth_bid_qty"],
            depth_ask_qty=derivatives["depth_ask_qty"],
            depth_wall_side=derivatives["depth_wall_side"],
            depth_wall_price=derivatives["depth_wall_price"],
            liquidation_buy_qty=derivatives["liquidation_buy_qty"],
            liquidation_sell_qty=derivatives["liquidation_sell_qty"],
            liquidation_imbalance=derivatives["liquidation_imbalance"],
            liquidation_spike=derivatives["liquidation_spike"],
            vwap=candle_context["vwap"],
            session_high=candle_context["session_high"],
            session_low=candle_context["session_low"],
            session_position=candle_context["session_position"],
            volume_zscore=candle_context["volume_zscore"],
            mtf_bias=mtf_context["mtf_bias"],
            mtf_alignment_score=mtf_context["mtf_alignment_score"],
            mtf_trends=mtf_context["mtf_trends"],
            candles=candles,
        )


def interval_to_ms(interval: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    unit = interval[-1]
    if unit not in units:
        raise ValueError(f"Unsupported interval: {interval}")
    return int(interval[:-1]) * units[unit]


def market_data_period(interval: str) -> str:
    allowed = {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}
    if interval == "1m":
        return "5m"
    return interval if interval in allowed else "15m"


def trend_from_candles(candles: list[list[float]]) -> str:
    if len(candles) < 30:
        return "mixed"
    closes = [row[3] for row in candles]
    fast = sum(closes[-5:]) / 5
    medium = sum(closes[-10:]) / 10
    slow = sum(closes[-30:]) / 30
    if fast > medium > slow:
        return "bullish"
    if fast < medium < slow:
        return "bearish"
    return "mixed"
