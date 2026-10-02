// frontend/src/lib/tracking-api.ts
// SERVER-ONLY calls for the two public attribution endpoints: the tracked
// WhatsApp link (/wa/[token]) and the inbound "how did you hear about us?"
// webhook (/hooks/heard-about-us). No admin credential is ever sent — the
// click token / per-client webhook secret are the only identifiers.
import "server-only"

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

// Hosts a tracked click may send a visitor to. Mirrors WHATSAPP_REDIRECT_HOSTS
// in backend app/core/constants.py.
const WHATSAPP_HOSTS = new Set(["wa.me", "api.whatsapp.com", "web.whatsapp.com"])

export function safeWhatsAppUrl(raw: string | null): string | null {
  if (!raw || raw.length > 2000) return null
  try {
    const url = new URL(raw)
    if (url.protocol !== "https:" || !WHATSAPP_HOSTS.has(url.hostname.toLowerCase())) return null
    if (url.username || url.password || url.port) return null
    return url.toString()
  } catch {
    return null
  }
}

export interface ClickContext {
  fallback: string | null
  ref: string | null
  utm: string | null
  visitorIp: string | null
  userAgent: string | null
  referer: string | null
}

// The WhatsApp URL to send the visitor to, or null when the backend has no
// answer (unknown token, nowhere safe to go, or the API is unreachable).
export async function resolveWhatsAppClick(token: string, ctx: ClickContext): Promise<string | null> {
  const params = new URLSearchParams()
  if (ctx.fallback) params.set("fallback", ctx.fallback.slice(0, 2000))
  if (ctx.ref) params.set("ref", ctx.ref.slice(0, 255))
  if (ctx.utm) params.set("utm", ctx.utm.slice(0, 255))
  const headers: Record<string, string> = {}
  if (ctx.visitorIp) headers["X-Visitor-IP"] = ctx.visitorIp.slice(0, 64)
  if (ctx.userAgent) headers["X-Visitor-UA"] = ctx.userAgent.slice(0, 512)
  if (ctx.referer) headers["X-Visitor-Referer"] = ctx.referer.slice(0, 2000)
  try {
    const res = await fetch(
      `${BASE}/api/v1/track/whatsapp/${encodeURIComponent(token)}?${params.toString()}`,
      { headers, cache: "no-store", signal: AbortSignal.timeout(3000) },
    )
    if (!res.ok) return null
    const body = (await res.json()) as { redirect_url?: string }
    return safeWhatsAppUrl(body.redirect_url ?? null)
  } catch {
    return null
  }
}

// Forwards the webhook body and secret untouched; the backend validates both.
export async function forwardHeardAboutUs(
  body: string,
  secret: string | null,
  authorization: string | null,
): Promise<{ status: number; body: string }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (secret) headers["X-SeenBy-Secret"] = secret
  if (authorization) headers["Authorization"] = authorization
  const res = await fetch(`${BASE}/api/v1/webhooks/heard-about-us`, {
    method: "POST",
    headers,
    body,
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  })
  return { status: res.status, body: await res.text() }
}
