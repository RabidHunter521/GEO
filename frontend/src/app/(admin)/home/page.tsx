// frontend/src/app/(admin)/home/page.tsx
// Admin home — the post-login landing. Greeting + the pending-work inbox (same
// buckets as /review-queue). Server component: the data fetch is server-side
// (api.ts is server-only) and filters/session are read on the server.
import Link from "next/link"
import { auth } from "../../../../auth"
import { getAllOutcomeActions, getClients } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { groupOutcomeActions } from "@/lib/review-queue-buckets"
import { HomeGreeting } from "./HomeGreeting"

export const dynamic = "force-dynamic"

export default async function HomePage() {
  const session = await auth()
  const name = session?.user?.name ?? "Admin"

  const clients = await getClients()
  const lists = await Promise.all(
    clients.map(async (client) => ({ client, actions: await getAllOutcomeActions(client.id) })),
  )
  const today = new Date().toISOString().slice(0, 10)
  const { sections, totalItems, clientCount } = groupOutcomeActions(lists, today)
  const activeSections = sections.filter((section) => section.items.length > 0)

  return (
    <div className="space-y-6">
      <HomeGreeting name={name} totalItems={totalItems} clientCount={clientCount} />

      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold tracking-tight">
          Action Required{totalItems > 0 ? ` (${totalItems})` : ""}
        </h2>
        <Link href="/review-queue" className="text-sm text-primary hover:underline">
          View full Review Queue →
        </Link>
      </div>

      {totalItems === 0 ? (
        <div className="rounded-md border bg-card py-12 text-center">
          <p className="text-sm text-muted-foreground">
            Nothing in the queue right now.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {activeSections.map((section) => (
            <section key={section.title}>
              <div className="mb-2 flex items-center justify-between border-b pb-2">
                <h3 className="text-sm font-semibold">{section.title}</h3>
                <Badge variant="secondary">{section.items.length}</Badge>
              </div>
              <div className="divide-y rounded-md border bg-card">
                {section.items.map(({ action, client }) => (
                  <Link
                    key={action.id}
                    href={`/clients/${client.id}/delivery`}
                    className="flex items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-muted/30"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{action.title}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {client.name}
                        {action.due_date ? ` · Due ${action.due_date}` : ""}
                      </p>
                    </div>
                    <Badge variant="outline">{action.priority}</Badge>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
