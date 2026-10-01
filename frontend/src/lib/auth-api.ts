// frontend/src/lib/auth-api.ts
// SERVER-ONLY calls to the API's sign-in / invite-link routes. These run
// before anyone is signed in, so they use the service credential (the raw
// ADMIN_API_KEY) rather than a user token.
import "server-only"

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

function serviceHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${process.env.ADMIN_API_KEY}`,
  }
}

export interface InviteLinkInfo {
  email: string
  name: string
  is_reset: boolean
  totp_secret: string
  otpauth_uri: string
}

export async function getInviteLink(token: string): Promise<InviteLinkInfo | null> {
  const res = await fetch(`${BASE}/api/v1/auth/link/${encodeURIComponent(token)}`, {
    headers: serviceHeaders(),
    cache: "no-store",
  })
  if (res.status === 404 || res.status === 422) return null
  if (!res.ok) throw new Error(`Invite link lookup failed (${res.status})`)
  return res.json()
}

export async function acceptInviteLink(
  token: string,
  password: string,
  code: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const res = await fetch(`${BASE}/api/v1/auth/link/${encodeURIComponent(token)}/accept`, {
    method: "POST",
    headers: serviceHeaders(),
    body: JSON.stringify({ password, code }),
    cache: "no-store",
  })
  if (res.ok) return { ok: true }
  let error = "Something went wrong. Please try again."
  try {
    const body = await res.json()
    if (typeof body?.detail === "string") error = body.detail
  } catch {
    // keep the generic message
  }
  return { ok: false, error }
}
