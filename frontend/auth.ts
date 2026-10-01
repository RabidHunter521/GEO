import NextAuth from "next-auth"
import Credentials from "next-auth/providers/credentials"

// Best-effort brute-force throttle in front of the API's own per-account
// lockout. The map lives in the Node process that serves /api/auth, so it is
// per-instance and resets on redeploy; it fails fast before the API is asked.
const MAX_FAILED_ATTEMPTS = 5
const LOCKOUT_MS = 15 * 60 * 1000
const loginAttempts = new Map<string, { count: number; firstAt: number }>()

// Global backstop: the per-email map alone lets an attacker rotate emails to
// get a fresh 5-attempt budget each, so total failures across all emails are
// capped per window too. Higher than the per-email cap to leave room for a
// small team fat-fingering their logins.
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

type LoginOutcome =
  | { kind: "user"; user: { id: string; email: string; name: string; role: "owner" | "staff"; workspace_id: string } }
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
  return { kind: "rejected" }
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
          return { id: u.id, email: u.email, name: u.name, role: u.role, workspaceId: u.workspace_id }
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
      }
      return token
    },
    session({ session, token }) {
      session.user.id = token.uid ?? ""
      session.user.role = token.role ?? "staff"
      session.user.workspaceId = token.workspaceId ?? ""
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
