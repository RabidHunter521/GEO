// frontend/src/components/view/ScoreHistoryChart.tsx
// Inline SVG bar chart of overall score over time — server-rendered,
// no chart library. Bars are colored by score band.
import { getScoreBand } from "@/lib/score-utils"
import type { ClientViewScorePoint } from "@/types"

const BAND_TOKEN: Record<string, string> = {
  green: "var(--score-strong)",
  yellow: "var(--score-watch)",
  red: "var(--score-low)",
}

interface Props {
  points: ClientViewScorePoint[] // oldest → newest
}

export function ScoreHistoryChart({ points }: Props) {
  if (points.length < 2) return null

  const width = 560
  const height = 120
  const gap = 8
  const barWidth = Math.min((width - gap * (points.length - 1)) / points.length, 48)

  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-sm font-medium">Your score over time</p>
      <svg
        viewBox={`0 0 ${width} ${height + 24}`}
        className="mt-3 w-full"
        role="img"
        aria-label="Visibility score history"
      >
        {points.map((p, i) => {
          const clamped = Math.max(0, Math.min(100, p.overall_score))
          const barHeight = Math.max(4, (clamped / 100) * height)
          const x = i * (barWidth + gap)
          const band = getScoreBand(clamped)
          const date = new Date(p.computed_at)
          const label = date.toLocaleDateString("en-MY", { day: "numeric", month: "short" })
          return (
            <g key={p.computed_at}>
              <title>{`${label}: ${clamped.toFixed(0)} / 100`}</title>
              <rect
                x={x}
                y={height - barHeight}
                width={barWidth}
                height={barHeight}
                rx={4}
                fill={`hsl(${BAND_TOKEN[band.color]})`}
                opacity={i === points.length - 1 ? 1 : 0.55}
              />
              <text
                x={x + barWidth / 2}
                y={height - barHeight - 6}
                textAnchor="middle"
                className="fill-foreground"
                fontSize="11"
                fontWeight="600"
              >
                {clamped.toFixed(0)}
              </text>
              {points.length <= 8 && (
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
    </div>
  )
}
