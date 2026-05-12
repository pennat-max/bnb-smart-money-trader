import { NextRequest, NextResponse } from "next/server";

const backendUrl =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "https://bnb-smart-money-api-production.up.railway.app";

export async function GET(request: NextRequest) {
  const upstream = new URL("/api/signal", backendUrl);
  request.nextUrl.searchParams.forEach((value, key) => {
    upstream.searchParams.set(key, value);
  });

  let response: Response;
  try {
    response = await fetch(upstream, { cache: "no-store" });
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
