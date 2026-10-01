// Fields our Credentials provider adds to the Auth.js user, JWT and session.
import type { DefaultSession } from "next-auth"

declare module "next-auth" {
  interface User {
    role?: "owner" | "staff"
    workspaceId?: string
  }
  interface Session {
    user: {
      id: string
      role: "owner" | "staff"
      workspaceId: string
    } & DefaultSession["user"]
  }
}

declare module "@auth/core/jwt" {
  interface JWT {
    uid?: string
    role?: "owner" | "staff"
    workspaceId?: string
  }
}
