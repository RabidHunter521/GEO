// frontend/src/app/(admin)/team/page.tsx
// Team: the admins who can sign in to this workspace. Owner only.
import { notFound } from "next/navigation"
import { getTeam } from "@/lib/api"
import { getCurrentAdmin } from "@/lib/current-admin"
import { TeamManager } from "./TeamManager"

export const dynamic = "force-dynamic"

export default async function TeamPage() {
  const admin = await getCurrentAdmin()
  if (!admin.isOwner) notFound()
  const members = await getTeam()
  return <TeamManager members={members} currentUserId={admin.id} />
}
