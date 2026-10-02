// Inbound "how did you hear about us?" webhook for form tools / CRMs / Zapier.
// Authenticated by the per-client secret (X-SeenBy-Secret or Bearer), which
// the backend checks; this handler only relays. Public by design — see
// middleware.ts.
import { NextRequest, NextResponse } from "next/server"
import { forwardHeardAboutUs } from "@/lib/tracking-api"

const MAX_BODY_BYTES = 16_384

export async function POST(req: NextRequest) {
  const body = await req.text()
  if (body.length > MAX_BODY_BYTES) {
    return NextResponse.json({ detail: "Payload too large" }, { status: 413 })
  }
  try {
    const upstream = await forwardHeardAboutUs(
      body,
      req.headers.get("x-seenby-secret"),
      req.headers.get("authorization"),
    )
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    })
  } catch {
    // 503 so the sender's retry logic tries again; submission_id makes the
    // retry safe.
    return NextResponse.json({ detail: "Temporarily unavailable" }, { status: 503 })
  }
}
