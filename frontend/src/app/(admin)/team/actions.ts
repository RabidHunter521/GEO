"use server"
// Team management server actions. The API enforces owner-only; errors carry
// the API's own message (e.g. "An account with that email already exists").
import { revalidatePath } from "next/cache"
import { ApiError, inviteTeamMember, resetTeamMember, setTeamMemberActive } from "@/lib/api"
import type { TeamLinkIssued, TeamRole } from "@/types"

type Result<T> = { ok: true; data: T } | { ok: false; error: string }

async function run<T>(fn: () => Promise<T>): Promise<Result<T>> {
  try {
    const data = await fn()
    revalidatePath("/team")
    return { ok: true, data }
  } catch (e) {
    return { ok: false, error: e instanceof ApiError ? e.message : "Something went wrong. Please try again." }
  }
}

export async function inviteAction(email: string, name: string, role: TeamRole): Promise<Result<TeamLinkIssued>> {
  return run(() => inviteTeamMember({ email, name, role }))
}

export async function resetAction(id: string): Promise<Result<TeamLinkIssued>> {
  return run(() => resetTeamMember(id))
}

export async function setActiveAction(id: string, active: boolean): Promise<Result<null>> {
  return run(async () => {
    await setTeamMemberActive(id, active)
    return null
  })
}
