import Link from "next/link"
import { getAllOutcomeActions, getClients } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { OutcomeAction } from "@/types"

const queueSections: { title: string; matches: (action: OutcomeAction, today: string) => boolean }[] = [
  { title: "Accuracy review", matches: (action) => action.action_type === "accuracy_review" && ["detected", "recommended", "approved_internal"].includes(action.status) },
  { title: "Client approval", matches: (action) => action.status === "waiting_client" },
  { title: "Publish-ready", matches: (action) => action.status === "ready_to_publish" },
  { title: "Verification-ready", matches: (action) => action.status === "waiting_verification" },
  { title: "Overdue", matches: (action, today) => Boolean(action.due_date && action.due_date < today && !["verified", "no_change", "superseded", "dismissed"].includes(action.status)) },
]

export default async function ReviewQueuePage() {
  const clients = await getClients()
  const lists = await Promise.all(clients.map(async (client) => ({ client, actions: await getAllOutcomeActions(client.id) })))
  const today = new Date().toISOString().slice(0, 10)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Review Queue</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">Outcome actions that need an operating decision.</p>
      </div>
      {queueSections.map((section) => {
        const items = lists.flatMap(({ client, actions }) => actions.filter((action) => section.matches(action, today)).map((action) => ({ action, client })))
        return (
          <section key={section.title}>
            <div className="mb-2 flex items-center justify-between border-b pb-2"><h2 className="text-sm font-semibold">{section.title}</h2><Badge variant="secondary">{items.length}</Badge></div>
            {items.length === 0 ? <p className="py-4 text-sm text-muted-foreground">No actions in this section.</p> : <div className="divide-y rounded-md border bg-card">
              {items.map(({ action, client }) => <Link key={action.id} href={`/clients/${client.id}/delivery`} className="flex items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-muted/30">
                <div className="min-w-0"><p className="truncate text-sm font-medium">{action.title}</p><p className="mt-0.5 text-xs text-muted-foreground">{client.name}{action.due_date ? ` · Due ${action.due_date}` : ""}</p></div><Badge variant="outline">{action.priority}</Badge>
              </Link>)}
            </div>}
          </section>
        )
      })}
      <div className="border-t pt-4"><Button variant="outline" size="sm" asChild><Link href="/review-queue/legacy-work-log">Legacy work-log suggestions</Link></Button></div>
    </div>
  )
}
