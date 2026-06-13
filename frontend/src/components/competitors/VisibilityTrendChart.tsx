// frontend/src/components/competitors/VisibilityTrendChart.tsx
// Multi-series inline-SVG line chart for visibility frequency over time.
// Server-renderable, no chart library — same philosophy as ScoreHistoryChart.

interface TrendChartSeries {
  name: string
  isYou: boolean
  points: (number | null)[]
}

interface Props {
  dates: string[] // ISO strings, oldest → newest, aligned with every series' points
  series: TrendChartSeries[]
  heading?: string
}

const WIDTH = 640
const HEIGHT = 200
const PAD_X = 16
const PAD_TOP = 12
const PAD_BOTTOM = 28

// Distinct muted strokes for up to 5 competitors
const COMPETITOR_STYLES = [
  { stroke: "#f59e0b", dash: "" },
  { stroke: "#8b5cf6", dash: "5 3" },
  { stroke: "#0ea5e9", dash: "2 3" },
  { stroke: "#ec4899", dash: "7 3" },
  { stroke: "#64748b", dash: "1 3" },
]

function x(i: number, count: number): number {
  if (count === 1) return WIDTH / 2
  return PAD_X + (i / (count - 1)) * (WIDTH - PAD_X * 2)
}

function y(value: number): number {
  const usable = HEIGHT - PAD_TOP - PAD_BOTTOM
  return PAD_TOP + (1 - Math.max(0, Math.min(100, value)) / 100) * usable
}

// Split a series into contiguous segments so null points break the line
function segments(points: (number | null)[]): { i: number; v: number }[][] {
  const out: { i: number; v: number }[][] = []
  let current: { i: number; v: number }[] = []
  points.forEach((v, i) => {
    if (v === null || v === undefined) {
      if (current.length) out.push(current)
      current = []
    } else {
      current.push({ i, v })
    }
  })
  if (current.length) out.push(current)
  return out
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-MY", { day: "numeric", month: "short" })
}

export function VisibilityTrendChart({ dates, series, heading }: Props) {
  if (dates.length < 2 || series.length === 0) return null

  let competitorIndex = -1

  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-sm font-medium">{heading ?? "Visibility frequency over time"}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        How often each brand was seen by AI on each scan (0–100%).
      </p>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mt-3 w-full"
        role="img"
        aria-label={heading ?? "Visibility frequency over time"}
      >
        {/* gridlines at 0/50/100 */}
        {[0, 50, 100].map((g) => (
          <g key={g}>
            <line
              x1={PAD_X} x2={WIDTH - PAD_X} y1={y(g)} y2={y(g)}
              stroke="currentColor" className="text-border" strokeWidth="1"
            />
            <text
              x={PAD_X} y={y(g) - 3}
              className="fill-muted-foreground" fontSize="9"
            >
              {g}%
            </text>
          </g>
        ))}

        {series.map((s) => {
          const style = s.isYou
            ? { stroke: "hsl(var(--primary))", dash: "" }
            : COMPETITOR_STYLES[++competitorIndex % COMPETITOR_STYLES.length]
          return (
            <g key={s.name} opacity={s.isYou ? 1 : 0.75}>
              {segments(s.points).map((seg, segIdx) => (
                <polyline
                  key={segIdx}
                  fill="none"
                  stroke={style.stroke}
                  strokeWidth={s.isYou ? 2.5 : 1.5}
                  strokeDasharray={style.dash}
                  strokeLinecap="round"
                  points={seg.map((p) => `${x(p.i, dates.length)},${y(p.v)}`).join(" ")}
                />
              ))}
              {s.points.map((v, i) =>
                v === null || v === undefined ? null : (
                  <circle
                    key={i}
                    cx={x(i, dates.length)} cy={y(v)}
                    r={s.isYou ? 3 : 2.5}
                    fill={style.stroke}
                  >
                    <title>{`${s.name} · ${shortDate(dates[i])} · ${Math.round(v)}%`}</title>
                  </circle>
                ),
              )}
            </g>
          )
        })}

        {/* x-axis date labels when readable */}
        {dates.length <= 8 &&
          dates.map((d, i) => (
            <text
              key={i}
              x={x(i, dates.length)} y={HEIGHT - 8}
              textAnchor="middle" fontSize="9"
              className="fill-muted-foreground"
            >
              {shortDate(d)}
            </text>
          ))}
      </svg>

      {/* legend */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {(() => {
          let legendIdx = -1
          return series.map((s) => {
            const color = s.isYou
              ? "hsl(var(--primary))"
              : COMPETITOR_STYLES[++legendIdx % COMPETITOR_STYLES.length].stroke
            return (
              <span key={s.name} className="flex items-center gap-1.5 text-xs">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className={s.isYou ? "font-semibold" : "text-muted-foreground"}>
                  {s.name}
                  {s.isYou && " (you)"}
                </span>
              </span>
            )
          })
        })()}
      </div>
    </div>
  )
}
