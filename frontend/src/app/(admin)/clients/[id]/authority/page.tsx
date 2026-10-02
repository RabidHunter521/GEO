import { getAuthorityView, getAuthorityCatalog, getPlacements } from "@/lib/api"
import { PlacementSection } from "@/components/placements/PlacementSection"
import { AuthorityClient } from "./AuthorityClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function AuthorityPage({ params }: Props) {
  const { id } = await params
  const [view, catalog, placements] = await Promise.all([
    getAuthorityView(id).catch(() => ({
      assets: [], suggested_next: [],
      summary: { total: 0, live: 0, verified: 0, covered_top_domains: 0, total_top_domains: 0 },
    })),
    getAuthorityCatalog(id).catch(() => []),
    getPlacements(id).catch(() => []),
  ])
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold tracking-tight">Authority &amp; Presence</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Track this client&apos;s directory, review, social, and knowledge-graph presence — prioritised
          by the sources AI answers actually drew from.
        </p>
      </div>
      <PlacementSection clientId={id} initialTargets={placements} />
      <AuthorityClient clientId={id} initialView={view} catalog={catalog} />
    </div>
  )
}
