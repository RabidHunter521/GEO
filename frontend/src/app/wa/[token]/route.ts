// Tracked WhatsApp link: /wa/<token>. Records the click (AI-attributed when the
// visitor first reached the site from an AI assistant) and sends the visitor
// on to WhatsApp. Public by design — see middleware.ts.
//
// A customer must never be stranded here: if the API is down or the token is
// unknown, a valid WhatsApp fallback link (passed by the website snippet) is
// still followed. Redirects only ever go to WhatsApp, so this is not an open
// redirect.
import { NextRequest, NextResponse } from "next/server"
import { resolveWhatsAppClick, safeWhatsAppUrl } from "@/lib/tracking-api"

const HEADERS = {
  "Cache-Control": "no-store",
  "X-Robots-Tag": "noindex, nofollow",
  "Referrer-Policy": "no-referrer",
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params
  const search = req.nextUrl.searchParams
  const fallback = search.get("fallback")
  const forwardedFor = req.headers.get("x-forwarded-for")

  const target =
    (await resolveWhatsAppClick(token, {
      fallback,
      ref: search.get("ref"),
      utm: search.get("utm"),
      visitorIp: forwardedFor?.split(",")[0]?.trim() || req.headers.get("x-real-ip"),
      userAgent: req.headers.get("user-agent"),
      referer: req.headers.get("referer"),
    })) ?? safeWhatsAppUrl(fallback)

  if (!target) {
    return new NextResponse("Not found", { status: 404, headers: HEADERS })
  }
  const res = NextResponse.redirect(target, 302)
  for (const [key, value] of Object.entries(HEADERS)) res.headers.set(key, value)
  return res
}
