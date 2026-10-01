import NextAuth from "next-auth"
import Credentials from "next-auth/providers/credentials"
import { verifyTotp } from "@/lib/totp"

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

// Legacy-login two-factor: when ADMIN_TOTP_SECRET (base32) is set, the env
// login also needs a 6-digit code. (Admin accounts always need one; that is
// enforced by the API.) The last accepted time step is remembered so a code that was
// just used (e.g. shoulder-surfed) cannot be replayed within its 30 s window.
let lastAcceptedTotpStep = -1

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

type LoginOutcome =
  | { kind: "user"; user: { id: string; email: string; name: string; role: "owner" | "staff"; workspace_id: string } }
  | { kind: "no_users" }
  | { kind: "rejected" }

// Ask the API to check an admin account (password + 2FA + lockout live there).
async function backendLogin(email: string, password: string, code: string): Promise<LoginOutcome> {
  const res = await fetch(`${process.env.API_BASE_URL ?? "http://localhost:8000"}/api/v1/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.ADMIN_API_KEY}`,
    },
    body: JSON.stringify({ email, password, code }),
    cache: "no-store",
  })
  if (res.ok) return { kind: "user", user: await res.json() }
  if (res.status === 409) return { kind: "no_users" }
  return { kind: "rejected" }
}

// The original single-admin login from env vars. Only reachable while no
// admin account has been set up (the API answers 409 no_users); from the
// moment the owner account exists, this path can never be taken again.
async function legacyEnvLogin(username: string, password: string, code: string) {
  const adminUser = process.env.ADMIN_USERNAME
  const adminPass = process.env.ADMIN_PASSWORD
  // Fail closed if admin credentials are not configured
  if (!adminUser || !adminPass) return null
  if (safeEqual(username, adminUser) && safeEqual(password, adminPass)) {
    const totpSecret = process.env.ADMIN_TOTP_SECRET
    if (totpSecret) {
      const step = await verifyTotp(totpSecret, code).catch(() => null)
      if (step === null || step <= lastAcceptedTotpStep) return null
      lastAcceptedTotpStep = step
    }
    return {
      id: "admin",
      name: process.env.ADMIN_DISPLAY_NAME || "Admin",
      email: "admin@seenby.my",
      role: "owner" as const,
      workspaceId: "",
      legacy: true,
    }
  }
  return null
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Self-hosted: trust the Host header from our own reverse proxy / server.
  // Without this, auth() fails with UntrustedHost in middleware and pages
  // would render without a session check.
  trustHost: true,
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "text" },
        password: { label: "Password", type: "password" },
        code: { label: "Authenticator code", type: "text" },
      },
      async authorize(credentials) {
        const email = credentials?.email
        const password = credentials?.password
        const code = typeof credentials?.code === "string" ? credentials.code : ""
        if (typeof email !== "string" || typeof password !== "string") return null
        const key = email.trim().toLowerCase()
        // In-process throttle in front of the API's own per-account lockout:
        // a locked key fails fast without revealing whether it exists.
        if (isLockedOut(key)) return null

        let outcome: LoginOutcome
        try {
          outcome = await backendLogin(email, password, code)
        } catch {
          return null // API unreachable: fail closed
        }
        if (outcome.kind === "user") {
          loginAttempts.delete(key)
          globalFailures = null
          const u = outcome.user
          return { id: u.id, email: u.email, name: u.name, role: u.role, workspaceId: u.workspace_id, legacy: false }
        }
        if (outcome.kind === "no_users") {
          const legacy = await legacyEnvLogin(email, password, code)
          if (legacy) {
            loginAttempts.delete(key)
            globalFailures = null
            return legacy
          }
        }
        recordFailure(key)
        return null
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      // `user` is only present on sign-in; copy our fields into the JWT once.
      if (user) {
        token.uid = user.id
        token.role = user.role
        token.workspaceId = user.workspaceId
        token.legacy = user.legacy ?? false
      }
      return token
    },
    session({ session, token }) {
      session.user.id = token.uid ?? ""
      session.user.role = token.role ?? "staff"
      session.user.workspaceId = token.workspaceId ?? ""
      session.user.legacy = token.legacy ?? false
      return session
    },
  },
  pages: {
    signIn: "/auth/login",
  },
  session: {
    strategy: "jwt",
    // An admin session can trigger paid scans; re-sign-in weekly. The API
    // re-checks the account on every request, so a deactivated admin loses
    // access immediately regardless.
    maxAge: 7 * 24 * 60 * 60,
  },
})
