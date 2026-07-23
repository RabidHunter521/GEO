import { getPageAudits } from "@/lib/api"
import { PageAuditsSection } from "./PageAuditsSection"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ContentStudioPage({ params }: Props) {
  const { id } = await params
  const audits = await getPageAudits(id).catch(() => [])
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold tracking-tight">Content Studio</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Page-level AI readability audits and publish-ready content drafts.
        </p>
      </div>
      <PageAuditsSection clientId={id} initialAudits={audits} />
    </div>
  )
}
