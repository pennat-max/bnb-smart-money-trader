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

export async function GET() {
  return proxy(new URL("/api/research/mission/latest", backendUrl));
}

export async function POST(request: NextRequest) {
  return proxy(new URL("/api/research/mission/start", backendUrl), {
    body: await request.text(),
    headers: { "content-type": request.headers.get("content-type") ?? "application/json" },
    method: "POST"
  });
}

async function proxy(upstream: URL, init?: RequestInit) {
  try {
    const response = await fetch(upstream, { cache: "no-store", ...init });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" }
    });
  } catch (error) {
    return NextResponse.json(
      { error: "backend_unreachable", message: error instanceof Error ? error.message : "Unknown backend fetch error" },
      { status: 502 }
    );
  }
}
