import { redirect } from "next/navigation"
import { auth } from "../../../auth"
import { Sidebar, MobileSidebar } from "@/components/layout/Sidebar"
import { getSuggestedWorkLogCount } from "@/lib/api"
import { isAuthenticatedAdmin } from "@/lib/session-guard"
import { getCurrentAdmin } from "@/lib/current-admin"

export default async function ClientsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Second auth layer behind middleware — admin pages must fail closed.
  // Validated, not just present: an error-populated auth object is truthy but
  // is not a session (see isAuthenticatedAdmin).
  const session = await auth()
  if (!isAuthenticatedAdmin(session)) redirect("/auth/login")

  // Best-effort: this layout wraps every admin page, so a failing count must
  // never take the sidebar (and with it the whole panel) down. No badge is a
  // fine degradation; a crash is not.
  let suggestedCount = 0
  try {
    suggestedCount = await getSuggestedWorkLogCount()
  } catch {
    suggestedCount = 0
  }

  const { isOwner } = await getCurrentAdmin()

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar suggestedCount={suggestedCount} isOwner={isOwner} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <MobileSidebar suggestedCount={suggestedCount} isOwner={isOwner} />
        <main className="flex-1 overflow-y-auto bg-app-wash p-4 md:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  )
}
