// frontend/src/lib/current-admin.ts
// SERVER-ONLY: who is signed in, for hiding controls a role can't use. The
// API enforces the same rules; this only keeps the UI honest.
import "server-only"
import { auth } from "../../auth"

export interface CurrentAdmin {
  name: string
  role: "owner" | "staff"
  isOwner: boolean
}

export async function getCurrentAdmin(): Promise<CurrentAdmin> {
  const session = await auth()
  const user = session?.user
  // Legacy single-admin login = the owner.
  const role = user?.legacy ? "owner" : user?.role === "owner" ? "owner" : "staff"
  return { name: user?.name ?? "Admin", role, isOwner: role === "owner" }
}
