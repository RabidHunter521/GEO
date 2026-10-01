// frontend/src/lib/api-token.ts
// SERVER-ONLY. The Authorization header for admin API calls.
//
// A signed-in admin gets a fresh 5-minute user token per request (HS256,
// aud "seenby-api"), so the API knows WHO is calling. The signing key is
// HMAC-SHA256(ADMIN_API_KEY, "seenby-user-token-v1") — mirrored in backend
// app/core/auth.py user_token_key(); the raw key itself never signs tokens
// and is not accepted on admin routes. No session → throws: admin API calls
// fail closed.
import "server-only"
import { SignJWT } from "jose"
import { auth } from "../../auth"
import { isAuthenticatedAdmin } from "@/lib/session-guard"

const KEY_LABEL = "seenby-user-token-v1"
const AUDIENCE = "seenby-api"
const TOKEN_TTL_SECONDS = 5 * 60

let cached: { apiKey: string; key: Uint8Array } | null = null

async function signingKey(apiKey: string): Promise<Uint8Array> {
  if (cached?.apiKey === apiKey) return cached.key
  const hmacKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(apiKey),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  )
  const key = new Uint8Array(await crypto.subtle.sign("HMAC", hmacKey, new TextEncoder().encode(KEY_LABEL)))
  cached = { apiKey, key }
  return key
}

export async function mintUserToken(userId: string, workspaceId: string, apiKey: string): Promise<string> {
  return new SignJWT({ wid: workspaceId })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setSubject(userId)
    .setAudience(AUDIENCE)
    .setIssuedAt()
    .setExpirationTime(`${TOKEN_TTL_SECONDS}s`)
    .sign(await signingKey(apiKey))
}

export class NotSignedInError extends Error {
  constructor() {
    super("Not signed in")
  }
}

export async function adminAuthHeader(): Promise<string> {
  const apiKey = process.env.ADMIN_API_KEY
  if (!apiKey) throw new Error("ADMIN_API_KEY is not configured")
  const session = await auth()
  if (!isAuthenticatedAdmin(session)) throw new NotSignedInError()
  const user = session!.user
  if (!user.id || !user.workspaceId) throw new NotSignedInError()
  return `Bearer ${await mintUserToken(user.id, user.workspaceId, apiKey)}`
}
