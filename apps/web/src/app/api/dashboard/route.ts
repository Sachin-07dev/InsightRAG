import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const authorization = request.headers.get("authorization");
  const organization = request.headers.get("x-organization-id");
  if (!authorization?.startsWith("Bearer ") || !organization) {
    return NextResponse.json(
      { error: "Authentication required" },
      { status: 401 },
    );
  }
  const body = await request.text();
  if (body.length > 16_384) {
    return NextResponse.json({ error: "Request too large" }, { status: 413 });
  }
  const origin = process.env.API_INTERNAL_BASE_URL ?? "http://127.0.0.1:8000";
  const upstream = await fetch(
    new URL("/api/v1/visualization/dashboard", origin),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: authorization,
        "X-Organization-ID": organization,
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    },
  );
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "private, no-store",
    },
  });
}
