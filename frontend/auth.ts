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
        if (safeEqual(username, adminUser) && safeEqual(password, adminPass)) {
          return { id: "admin", name: "Admin", email: "admin@seenby.my" }
        }
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
