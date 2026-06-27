import NextAuth from "next-auth"
import Credentials from "next-auth/providers/credentials"

// Constant-time string comparison without node:crypto so this file stays
// edge-compatible (it is imported by middleware.ts).
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  }
  return diff === 0
}

// Best-effort brute-force throttle for the single admin login. The map lives in
// the Node process that serves /api/auth, so it is per-instance and resets on
// redeploy — acceptable for a self-hosted single-admin tool, and it raises the
// cost of an online password-guessing attack from unlimited to a trickle.
const MAX_FAILED_ATTEMPTS = 5
const LOCKOUT_MS = 15 * 60 * 1000
const loginAttempts = new Map<string, { count: number; firstAt: number }>()

// Global backstop: the per-username map alone lets an attacker rotate usernames
// to get a fresh 5-attempt budget each. There is exactly one valid username, so
// a flood of distinct usernames is always an attack — cap total failures across
// all usernames per window too. Higher than the per-username cap to leave room
// for an admin fat-fingering their own login a few times.
const MAX_GLOBAL_FAILED_ATTEMPTS = 20
let globalFailures: { count: number; firstAt: number } | null = null

function isLockedOut(key: string): boolean {
  if (
    globalFailures &&
    Date.now() - globalFailures.firstAt <= LOCKOUT_MS &&
    globalFailures.count >= MAX_GLOBAL_FAILED_ATTEMPTS
  ) {
    return true
  }
  const entry = loginAttempts.get(key)
  if (!entry) return false
  if (Date.now() - entry.firstAt > LOCKOUT_MS) {
    loginAttempts.delete(key) // window elapsed — start fresh
    return false
  }
  return entry.count >= MAX_FAILED_ATTEMPTS
}

function recordFailure(key: string): void {
  const entry = loginAttempts.get(key)
  if (!entry || Date.now() - entry.firstAt > LOCKOUT_MS) {
    loginAttempts.set(key, { count: 1, firstAt: Date.now() })
  } else {
    entry.count += 1
  }
  if (!globalFailures || Date.now() - globalFailures.firstAt > LOCKOUT_MS) {
    globalFailures = { count: 1, firstAt: Date.now() }
  } else {
    globalFailures.count += 1
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Self-hosted: trust the Host header from our own reverse proxy / server.
  // Without this, auth() fails with UntrustedHost in middleware and pages
  // would render without a session check.
  trustHost: true,
  providers: [
    Credentials({
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const adminUser = process.env.ADMIN_USERNAME
        const adminPass = process.env.ADMIN_PASSWORD
        // Fail closed if admin credentials are not configured
        if (!adminUser || !adminPass) return null
        const username = credentials?.username
        const password = credentials?.password
        if (typeof username !== "string" || typeof password !== "string") {
          return null
        }
        // Throttle before checking: a locked key fails fast without revealing
        // whether the username was right.
        if (isLockedOut(username)) {
          return null
        }
        if (safeEqual(username, adminUser) && safeEqual(password, adminPass)) {
          loginAttempts.delete(username) // success resets the per-user counter
          globalFailures = null // …and the global backstop
          return { id: "admin", name: "Admin", email: "admin@seenby.my" }
        }
        recordFailure(username)
        return null
      },
    }),
  ],
  pages: {
    signIn: "/auth/login",
  },
  session: {
    strategy: "jwt",
  },
})
