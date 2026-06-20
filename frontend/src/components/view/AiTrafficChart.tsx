// frontend/src/components/view/AiTrafficChart.tsx
// Inline SVG bar chart of monthly AI-referral visitors — server-rendered,
// no chart library. Mirrors ScoreHistoryChart's approach.
import type { ClientViewTrafficPoint } from "@/types"

interface Props {
  points: ClientViewTrafficPoint[] // oldest → newest
}

export function AiTrafficChart({ points }: Props) {
  if (points.length < 2) return null

  const recent = points.slice(-12)
  const max = Math.max(...recent.map((p) => p.ai_visitors), 1)
  const width = 560
  const height = 110
  const gap = 8
  const barWidth = (width - gap * (recent.length - 1)) / recent.length

  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-sm font-medium">AI visitors over time</p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Visitors arriving at your website via ChatGPT, Perplexity, Gemini and
        Claude — tracked by the SeenBy team.
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
          return (
            <g key={p.period}>
              <title>{`${label}: ${p.ai_visitors.toLocaleString()} visitors`}</title>
              <rect
                x={x}
                y={height - barHeight}
                width={barWidth}
                height={barHeight}
                rx={4}
                className="fill-primary"
                opacity={i === recent.length - 1 ? 1 : 0.5}
              />
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
    </div>
  )
}
