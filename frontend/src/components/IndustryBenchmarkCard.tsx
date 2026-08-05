// frontend/src/components/IndustryBenchmarkCard.tsx
// Anonymous industry standing card — shared by the admin client detail page
// and the read-only client view overview.
//
// LEGACY (Phase 6). Superseded by ClientBenchmarkCard, which the share view
// renders whenever an approved cohort snapshot exists for the client. This
// card remains the fallback until that is true for everyone, and it is the
// reason the fallback is time-limited rather than permanent: it shows an
// EXACT peer count, and on the admin page a rank — both of which Phase 6
// forbids, because an exact count that moves month to month reveals when one
// business joined or left, and a rank in a small group narrows down who the
// neighbours are. It also groups on the free-text `clients.industry` string
// with a floor of only 3 peers.
//
// Do not add features here. When every client has an approved snapshot,
// delete this component and its two call sites.
import { Trophy } from "lucide-react"

interface Props {
  industry: string
  topPercent: number
  peerCount: number
  industryAverage: number
  // Admin-only extras — never passed on the client share view
  clientScore?: number
  rank?: number
}

export function IndustryBenchmarkCard({
  industry,
  topPercent,
  peerCount,
  industryAverage,
  clientScore,
  rank,
}: Props) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-start gap-3">
        <Trophy className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
        <div>
          <p className="text-sm font-medium">
            You rank in the top {topPercent}% of {industry} businesses tracked by SeenBy
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Industry average: {industryAverage.toFixed(0)} &middot; based on {peerCount}{" "}
            businesses
            {rank !== undefined && clientScore !== undefined && (
              <span> &middot; rank #{rank} with a score of {clientScore.toFixed(0)}</span>
            )}
          </p>
        </div>
      </div>
    </div>
  )
}
