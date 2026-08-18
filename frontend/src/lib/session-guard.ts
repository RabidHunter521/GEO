// Shared admin-session validation for middleware.ts and the (admin) layout.
//
// Why this exists rather than `!!session`:
// Auth.js can populate the session/auth object with an ERROR rather than
// returning null when configuration or JWT decoding fails (GHSA-8fpg-xm3f-6cx3
// — "existence-based auth checks fail open"). Any check shaped like
// `!!req.auth` or `if (!session)` then reads that error object as truthy and
// admits an anonymous request. Middleware is the only gate in front of the
// entire admin panel here, so it must assert a positive identity, not the mere
// presence of an object.
//
// Edge-compatible: no node: imports, so middleware.ts can use it.

type MaybeSession = {
  user?: { email?: unknown } | null
  error?: unknown
} | null | undefined

/**
 * True only when the object is a real authenticated admin session:
 * no error marker, and a non-empty user email (the identity our Credentials
 * provider sets on every successful login).
 */
export function isAuthenticatedAdmin(session: MaybeSession): boolean {
  if (!session || typeof session !== "object") return false
  // An error-populated auth object is a failure, never a session.
  if ("error" in session && session.error) return false
  const user = session.user
  if (!user || typeof user !== "object") return false
  const email = (user as { email?: unknown }).email
  return typeof email === "string" && email.length > 0
}
