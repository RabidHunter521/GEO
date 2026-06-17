// frontend/src/components/scan/SinceLastScanCard.tsx
// Shows what changed between the two most recent completed scans.
// Language rules: "Seen by AI" / "Not seen by AI" / "visibility frequency" only.
import { CheckCircle, XCircle, ArrowRight } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { ScanDiffResponse, ScanDiffQuery } from "@/types"

const PLATFORM_LABELS: Record<string, string> = {
  chatgpt: "ChatGPT",
  perplexity: "Perplexity",
  gemini: "Gemini",
  claude: "Claude",
}

const CATEGORY_LABELS: Record<string, string> = {
  brand: "Brand",
  comparison: "Comparison",
  recommendation: "Recommendation",
  local: "Local",
}

interface Props {
  diff: ScanDiffResponse
}

export function SinceLastScanCard({ diff }: Props) {
  if (!diff.has_comparison) {
    return (
      <div className="rounded-lg border bg-card p-4">
        <p className="text-sm font-medium mb-0.5">Since last scan</p>
        <p className="text-sm text-muted-foreground">
          First scan — no comparison yet.
        </p>
      </div>
    )
  }

  const prevVis = diff.previous_visibility
  const latestVis = diff.latest_visibility
  const hasBoth = prevVis !== null && latestVis !== null
  const delta = hasBoth ? latestVis! - prevVis! : null

  return (
    <div className="rounded-lg border bg-card p-4 space-y-4">
      <div>
        <p className="text-sm font-medium">Since last scan</p>
        {hasBoth && (
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-muted-foreground">
              Visibility frequency:
            </span>
            <span className="flex items-center gap-1 text-sm font-semibold tabular-nums">
              <span className="text-muted-foreground">{prevVis!.toFixed(1)}%</span>
              <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
              <span
                className={
                  delta! > 0
                    ? "text-score-strong"
                    : delta! < 0
                      ? "text-destructive"
                      : "text-foreground"
                }
              >
                {latestVis!.toFixed(1)}%
              </span>
              {delta !== null && delta !== 0 && (
                <span
                  className={`text-xs font-normal ${delta > 0 ? "text-score-strong" : "text-destructive"}`}
                >
                  ({delta > 0 ? "+" : ""}
                  {delta.toFixed(1)} pts)
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      {diff.newly_seen.length === 0 && diff.newly_unseen.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No changes detected across matched queries.
        </p>
      )}

      {diff.newly_seen.length > 0 && (
        <QueryList
          title="Newly Seen by AI"
          queries={diff.newly_seen}
          variant="seen"
        />
      )}

      {diff.newly_unseen.length > 0 && (
        <QueryList
          title="Now Not seen by AI"
          queries={diff.newly_unseen}
          variant="unseen"
        />
      )}
    </div>
  )
}

function QueryList({
  title,
  queries,
  variant,
}: {
  title: string
  queries: ScanDiffQuery[]
  variant: "seen" | "unseen"
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        {variant === "seen" ? (
          <CheckCircle className="h-3.5 w-3.5 text-score-strong shrink-0" />
        ) : (
          <XCircle className="h-3.5 w-3.5 text-score-watch shrink-0" />
        )}
        <p
          className={`text-xs font-semibold ${
            variant === "seen" ? "text-score-strong" : "text-score-watch"
          }`}
        >
          {title}
        </p>
        <span className="text-xs text-muted-foreground">
          ({queries.length})
        </span>
      </div>
      <ul className="space-y-1.5">
        {queries.map((q) => (
          <li
            key={`${q.platform}:${q.category}:${q.query_text}`}
            className={`rounded-md px-3 py-2 text-sm ${
              variant === "seen"
                ? "bg-score-strong/5 border border-score-strong/20"
                : "bg-score-watch/5 border border-score-watch/20"
            }`}
          >
            <span className="text-muted-foreground">{q.query_text}</span>
            <div className="flex gap-1.5 mt-1">
              <Badge variant="outline" className="text-xs font-normal py-0">
                {PLATFORM_LABELS[q.platform] ?? q.platform}
              </Badge>
              <Badge variant="outline" className="text-xs font-normal py-0">
                {CATEGORY_LABELS[q.category] ?? q.category}
              </Badge>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
