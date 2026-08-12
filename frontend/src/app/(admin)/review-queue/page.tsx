import Link from "next/link"
import { getAllOutcomeActions, getClients } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { groupOutcomeActions } from "@/lib/review-queue-buckets"

export default async function ReviewQueuePage() {
  const clients = await getClients()
  const lists = await Promise.all(
    clients.map(async (client) => ({ client, actions: await getAllOutcomeActions(client.id) })),
  )
  const today = new Date().toISOString().slice(0, 10)
  const { sections } = groupOutcomeActions(lists, today)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Review Queue</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Outcome actions that need an operating decision.
        </p>
      </div>
      {sections.map((section) => (
        <section key={section.title}>
          <div className="mb-2 flex items-center justify-between border-b pb-2">
            <h2 className="text-sm font-semibold">{section.title}</h2>
            <Badge variant="secondary">{section.items.length}</Badge>
          </div>
          {section.items.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">No actions in this section.</p>
          ) : (
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
          )}
        </section>
      ))}
      <div className="border-t pt-4">
        <Button variant="outline" size="sm" asChild>
          <Link href="/review-queue/legacy-work-log">Legacy work-log suggestions</Link>
        </Button>
      </div>
    </div>
  )
}
