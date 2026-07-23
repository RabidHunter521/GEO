import { getPageAudits, getDeliverables, getCompetitorIntelligence } from "@/lib/api"
import { PageAuditsSection } from "./PageAuditsSection"
import { DeliverablesSection } from "./DeliverablesSection"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ContentStudioPage({ params }: Props) {
  const { id } = await params
  const [audits, deliverables, intel] = await Promise.all([
    getPageAudits(id).catch(() => []),
    getDeliverables(id).catch(() => []),
    getCompetitorIntelligence(id).catch(() => null),
  ])
  const competitors = (intel?.competitors ?? []).map((c) => ({ id: c.id, name: c.name ?? "Unnamed" }))
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold tracking-tight">Content Studio</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Page-level AI readability audits and publish-ready content drafts.
        </p>
      </div>
      <PageAuditsSection clientId={id} initialAudits={audits} />
      <DeliverablesSection
        clientId={id}
        initialDeliverables={deliverables}
        competitors={competitors}
      />
    </div>
  )
}
