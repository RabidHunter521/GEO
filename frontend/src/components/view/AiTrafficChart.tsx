// frontend/src/components/view/AiTrafficChart.tsx
// Inline SVG bar chart of monthly AI-referral visitors — server-rendered,
// no chart library. Mirrors ScoreHistoryChart's approach.
//
// Provenance is part of the chart, not a footnote we can drop: these numbers
// are either synced from the client's own GA4 property or typed in by the
// SeenBy team from a figure the client supplied. A bar axis reads as
// measurement either way, so a hand-entered month says so — on the caption,
// in its tooltip, and in how the bar is drawn.
import type { ClientViewTrafficPoint } from "@/types"

interface Props {
  points: ClientViewTrafficPoint[] // oldest → newest
}

const SOURCE_LABEL: Record<string, string> = {
  ga4: "synced from your website analytics",
  manual: "entered by the SeenBy team",
}

function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] ?? SOURCE_LABEL.manual
}

export function AiTrafficChart({ points }: Props) {
  if (points.length < 2) return null

  const recent = points.slice(-12)
  const max = Math.max(...recent.map((p) => p.ai_visitors), 1)
  const width = 560
  const height = 110
  const gap = 8
  const barWidth = Math.min((width - gap * (recent.length - 1)) / recent.length, 48)

  const syncedCount = recent.filter((p) => p.source === "ga4").length
  const manualCount = recent.length - syncedCount

  // One sentence that is true of the months actually on screen.
  let provenance: string
  if (manualCount === 0) {
    provenance = "Synced directly from your website analytics."
  } else if (syncedCount === 0) {
    provenance =
      "Figures you supplied, entered by the SeenBy team — not measured by SeenBy."
  } else {
    provenance = `${syncedCount} of these ${recent.length} months are synced from your website analytics; the other ${manualCount} were entered by the SeenBy team from figures you supplied.`
  }

  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-sm font-medium">AI visitors over time</p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Visitors arriving at your website via ChatGPT, Perplexity, Gemini and
        Claude.
      </p>
      <svg
        viewBox={`0 0 ${width} ${height + 24}`}
        className="mt-3 w-full"
        role="img"
        aria-label="AI referral traffic over time"
      >
        {recent.map((p, i) => {
          const barHeight = Math.max(4, (p.ai_visitors / max) * height)
          const x = i * (barWidth + gap)
          const date = new Date(p.period)
          const label = date.toLocaleDateString("en-MY", { month: "short" })
          const isManual = p.source !== "ga4"
          return (
            <g key={p.period}>
              <title>{`${label}: ${p.ai_visitors.toLocaleString()} visitors — ${sourceLabel(p.source)}`}</title>
              <rect
                x={x}
                y={height - barHeight}
                width={barWidth}
                height={barHeight}
                rx={4}
                className="fill-primary"
                opacity={i === recent.length - 1 ? 1 : 0.5}
              />
              {/* Hand-entered months carry a dashed outline so the reader can
                  tell them apart from synced ones without reading the caption.
                  Opacity already encodes recency, so provenance uses stroke. */}
              {isManual && (
                <rect
                  x={x}
                  y={height - barHeight}
                  width={barWidth}
                  height={barHeight}
                  rx={4}
                  fill="none"
                  strokeDasharray="3 2"
                  strokeWidth={1}
                  className="stroke-muted-foreground"
                />
              )}
              {recent.length <= 8 && (
                <text
                  x={x + barWidth / 2}
                  y={height - barHeight - 6}
                  textAnchor="middle"
                  className="fill-foreground"
                  fontSize="11"
                  fontWeight="600"
                >
                  {p.ai_visitors.toLocaleString("en-MY")}
                </text>
              )}
              {recent.length <= 8 && (
                <text
                  x={x + barWidth / 2}
                  y={height + 16}
                  textAnchor="middle"
                  className="fill-muted-foreground"
                  fontSize="10"
                >
                  {label}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      <p className="mt-2 text-xs text-muted-foreground">
        {manualCount > 0 && (
          <span
            aria-hidden
            className="mr-1.5 inline-block h-2.5 w-2.5 translate-y-[1px] rounded-[2px] border border-dashed border-muted-foreground"
          />
        )}
        {provenance}
      </p>
    </div>
  )
}
