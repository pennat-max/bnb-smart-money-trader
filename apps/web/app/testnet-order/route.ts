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

export async function POST(request: NextRequest) {
  const upstream = new URL("/api/testnet/order", backendUrl);

  let response: Response;
  try {
    response = await fetch(upstream, {
      body: await request.text(),
      cache: "no-store",
      headers: { "content-type": request.headers.get("content-type") ?? "application/json" },
      method: "POST"
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "backend_unreachable",
        message: error instanceof Error ? error.message : "Unknown backend fetch error",
        upstream: upstream.toString()
      },
      { status: 502 }
    );
  }

  const payload = await response.text();
  return new NextResponse(payload, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json"
    }
  });
}
