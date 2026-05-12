import { NextRequest, NextResponse } from "next/server";

const fallbackBackendUrl = "https://bnb-smart-money-api-production.up.railway.app";
const backendUrl = resolveBackendUrl();

function resolveBackendUrl() {
  for (const rawValue of [process.env.API_URL, process.env.NEXT_PUBLIC_API_URL, fallbackBackendUrl]) {
    const value = rawValue?.trim();
    if (!value) continue;
    try {
      const url = new URL(value);
      const isLocalhost = ["localhost", "127.0.0.1", "0.0.0.0"].includes(url.hostname);
      if (process.env.VERCEL && isLocalhost) continue;
      return url.origin;
    } catch {
      continue;
    }
  }
  return fallbackBackendUrl;
}

export async function GET(request: NextRequest) {
  const upstream = new URL("/api/derivatives", backendUrl);
  request.nextUrl.searchParams.forEach((value, key) => {
    upstream.searchParams.set(key, value);
  });

  try {
    const response = await fetch(upstream, { cache: "no-store" });
    const payload = await response.text();
    if (response.ok) {
      const parsed = JSON.parse(payload);
      if (parsed.data_ok) {
        return NextResponse.json(parsed);
      }
    }

    const symbol = request.nextUrl.searchParams.get("symbol") ?? "BNBUSDT";
    const period = normalizePeriod(request.nextUrl.searchParams.get("period") ?? "15m");
    return NextResponse.json(await fetchBinanceDerivatives(symbol, period));
  } catch (error) {
    try {
      const symbol = request.nextUrl.searchParams.get("symbol") ?? "BNBUSDT";
      const period = normalizePeriod(request.nextUrl.searchParams.get("period") ?? "15m");
      return NextResponse.json(await fetchBinanceDerivatives(symbol, period));
    } catch {
      return NextResponse.json(
        { error: "backend_unreachable", message: error instanceof Error ? error.message : "Unknown backend fetch error" },
        { status: 502 }
      );
    }
  }
}

function normalizePeriod(period: string) {
  if (period === "1m") return "5m";
  return ["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"].includes(period) ? period : "15m";
}

async function fetchBinanceDerivatives(symbol: string, period: string) {
  const baseUrl = "https://fapi.binance.com";
  const [oiResponse, ratioResponse, takerResponse, depthResponse] = await Promise.all([
    fetch(`${baseUrl}/futures/data/openInterestHist?symbol=${symbol}&period=${period}&limit=3`, { cache: "no-store" }),
    fetch(`${baseUrl}/futures/data/globalLongShortAccountRatio?symbol=${symbol}&period=${period}&limit=3`, { cache: "no-store" }),
    fetch(`${baseUrl}/futures/data/takerlongshortRatio?symbol=${symbol}&period=${period}&limit=3`, { cache: "no-store" }),
    fetch(`${baseUrl}/fapi/v1/depth?symbol=${symbol}&limit=50`, { cache: "no-store" })
  ]);

  const oiRows = oiResponse.ok ? await oiResponse.json() : [];
  const ratioRows = ratioResponse.ok ? await ratioResponse.json() : [];
  const takerRows = takerResponse.ok ? await takerResponse.json() : [];
  const depth = depthResponse.ok ? await depthResponse.json() : { bids: [], asks: [] };

  const previousOi = Number(oiRows.at(-2)?.sumOpenInterest ?? 0);
  const latestOi = Number(oiRows.at(-1)?.sumOpenInterest ?? previousOi);
  const latestRatio = ratioRows.at(-1) ?? {};
  const latestTaker = takerRows.at(-1) ?? {};
  const buyVol = Number(latestTaker.buyVol ?? 0);
  const sellVol = Number(latestTaker.sellVol ?? 0);
  const bidQty = (depth.bids ?? []).reduce((sum: number, row: string[]) => sum + Number(row[1] ?? 0), 0);
  const askQty = (depth.asks ?? []).reduce((sum: number, row: string[]) => sum + Number(row[1] ?? 0), 0);
  const strongestBid = strongestLevel(depth.bids ?? []);
  const strongestAsk = strongestLevel(depth.asks ?? []);
  const totalDepth = bidQty + askQty;
  const takerTotal = buyVol + sellVol;
  const openInterestChangePct = previousOi ? ((latestOi - previousOi) / previousOi) * 100 : 0;
  const longShortRatio = Number(latestRatio.longShortRatio ?? 1);
  const takerBuySellRatio = Number(latestTaker.buySellRatio ?? 1);
  const bidAskImbalance = totalDepth ? (bidQty - askQty) / totalDepth : 0;
  const wall = depthWall(strongestBid, strongestAsk);
  const hasProductionData = Boolean(oiRows.length || ratioRows.length || takerRows.length || totalDepth);

  if (!hasProductionData) {
    return fetchBinanceTestnetDerivatives(symbol, period);
  }

  const noteParts = [];

  if (longShortRatio > 1.6) noteParts.push("crowded longs");
  if (longShortRatio < 0.7) noteParts.push("crowded shorts");
  if (openInterestChangePct > 0.35) noteParts.push("OI expanding");
  if (takerBuySellRatio > 1.25) noteParts.push("taker buy pressure");
  if (takerBuySellRatio < 0.8) noteParts.push("taker sell pressure");
  if (bidAskImbalance > 0.12) noteParts.push("bid wall imbalance");
  if (bidAskImbalance < -0.12) noteParts.push("ask wall imbalance");

  return {
    symbol,
    period,
    source: "vercel_binance_public_futures",
    data_ok: hasProductionData,
    open_interest_change_pct: openInterestChangePct,
    long_short_ratio: longShortRatio,
    long_account: Number(latestRatio.longAccount ?? 0.5),
    short_account: Number(latestRatio.shortAccount ?? 0.5),
    taker_buy_sell_ratio: takerBuySellRatio,
    taker_buy_volume_ratio: takerTotal ? buyVol / takerTotal : 0.5,
    bid_ask_imbalance: bidAskImbalance,
    depth_bid_qty: bidQty,
    depth_ask_qty: askQty,
    depth_wall_side: wall.side,
    depth_wall_price: wall.price,
    liquidation_buy_qty: 0,
    liquidation_sell_qty: 0,
    liquidation_imbalance: 0,
    liquidation_spike: false,
    smart_money_note: noteParts.length ? noteParts.join(", ") : "no strong derivatives imbalance"
  };
}

async function fetchBinanceTestnetDerivatives(symbol: string, period: string) {
  const baseUrl = "https://testnet.binancefuture.com";
  const [openInterestResponse, premiumResponse, depthResponse] = await Promise.all([
    fetch(`${baseUrl}/fapi/v1/openInterest?symbol=${symbol}`, { cache: "no-store" }),
    fetch(`${baseUrl}/fapi/v1/premiumIndex?symbol=${symbol}`, { cache: "no-store" }),
    fetch(`${baseUrl}/fapi/v1/depth?symbol=${symbol}&limit=50`, { cache: "no-store" })
  ]);

  const openInterest = openInterestResponse.ok ? await openInterestResponse.json() : {};
  const premium = premiumResponse.ok ? await premiumResponse.json() : {};
  const depth = depthResponse.ok ? await depthResponse.json() : { bids: [], asks: [] };
  const bidQty = (depth.bids ?? []).reduce((sum: number, row: string[]) => sum + Number(row[1] ?? 0), 0);
  const askQty = (depth.asks ?? []).reduce((sum: number, row: string[]) => sum + Number(row[1] ?? 0), 0);
  const strongestBid = strongestLevel(depth.bids ?? []);
  const strongestAsk = strongestLevel(depth.asks ?? []);
  const totalDepth = bidQty + askQty;
  const bidAskImbalance = totalDepth ? (bidQty - askQty) / totalDepth : 0;
  const wall = depthWall(strongestBid, strongestAsk);
  const fundingRate = Number(premium.lastFundingRate ?? 0);
  const noteParts = [];

  if (bidAskImbalance > 0.12) noteParts.push("testnet bid wall imbalance");
  if (bidAskImbalance < -0.12) noteParts.push("testnet ask wall imbalance");
  if (fundingRate > 0.0001) noteParts.push("positive funding");
  if (fundingRate < -0.0001) noteParts.push("negative funding");
  if (Number(openInterest.openInterest ?? 0) > 0) noteParts.push("testnet OI online");

  return {
    symbol,
    period,
    source: "vercel_binance_futures_testnet_public",
    data_ok: Boolean(totalDepth || openInterest.openInterest || premium.markPrice),
    open_interest_change_pct: 0,
    long_short_ratio: 1,
    long_account: 0.5,
    short_account: 0.5,
    taker_buy_sell_ratio: 1,
    taker_buy_volume_ratio: 0.5,
    bid_ask_imbalance: bidAskImbalance,
    depth_bid_qty: bidQty,
    depth_ask_qty: askQty,
    depth_wall_side: wall.side,
    depth_wall_price: wall.price,
    liquidation_buy_qty: 0,
    liquidation_sell_qty: 0,
    liquidation_imbalance: 0,
    liquidation_spike: false,
    smart_money_note: noteParts.length
      ? `${noteParts.join(", ")}; production sentiment endpoints unavailable from this cloud`
      : "production sentiment endpoints unavailable from this cloud"
  };
}

function strongestLevel(levels: string[][]) {
  return levels.reduce(
    (best, row) => {
      const price = Number(row[0] ?? 0);
      const qty = Number(row[1] ?? 0);
      return qty > best.qty ? { price, qty } : best;
    },
    { price: 0, qty: 0 }
  );
}

function depthWall(bid: { price: number; qty: number }, ask: { price: number; qty: number }) {
  if (bid.qty > ask.qty * 1.35) return { side: "bid", price: bid.price };
  if (ask.qty > bid.qty * 1.35) return { side: "ask", price: ask.price };
  return { side: "neutral", price: null };
}
