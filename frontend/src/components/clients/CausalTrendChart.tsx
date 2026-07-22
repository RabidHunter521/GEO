// frontend/src/components/clients/CausalTrendChart.tsx
// Two-series inline-SVG line chart: "queries we optimized" vs "queries we
// left alone" — the causal proof. Server-renderable, no chart library;
// mirrors VisibilityTrendChart's approach.

interface Props {
  dates: string[] // ISO strings, oldest → newest, aligned with both series
  optimized: (number | null)[]
  leftAlone: (number | null)[]
  heading?: string
}

const WIDTH = 640
const HEIGHT = 200
const PAD_X = 16
const PAD_TOP = 12
const PAD_BOTTOM = 28

const OPTIMIZED_STYLE = { stroke: "hsl(var(--primary))", dash: "" }
const LEFT_ALONE_STYLE = { stroke: "#64748b", dash: "5 3" }

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

export function CausalTrendChart({ dates, optimized, leftAlone, heading }: Props) {
  if (dates.length < 2) return null

  const series = [
    { name: "Queries we optimized", points: optimized, style: OPTIMIZED_STYLE, main: true },
    { name: "Queries we left alone", points: leftAlone, style: LEFT_ALONE_STYLE, main: false },
  ]

  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-sm font-medium">
        {heading ?? "Queries we optimized vs. queries we left alone"}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        The queries we deliberately left untouched are the benchmark — when only
        the optimized ones climb, the movement is our work.
      </p>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mt-3 w-full"
        role="img"
        aria-label={heading ?? "Queries we optimized vs. queries we left alone"}
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

        {series.map((s) => (
          <g key={s.name} opacity={s.main ? 1 : 0.75}>
            {segments(s.points).map((seg, segIdx) => (
              <polyline
                key={segIdx}
                fill="none"
                stroke={s.style.stroke}
                strokeWidth={s.main ? 2.5 : 1.5}
                strokeDasharray={s.style.dash}
                strokeLinecap="round"
                points={seg.map((p) => `${x(p.i, dates.length)},${y(p.v)}`).join(" ")}
              />
            ))}
            {s.points.map((v, i) =>
              v === null || v === undefined ? null : (
                <circle
                  key={i}
                  cx={x(i, dates.length)} cy={y(v)}
                  r={s.main ? 3 : 2.5}
                  fill={s.style.stroke}
                >
                  <title>{`${s.name} · ${shortDate(dates[i])} · ${Math.round(v)}%`}</title>
                </circle>
              ),
            )}
          </g>
        ))}

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
        {series.map((s) => (
          <span key={s.name} className="flex items-center gap-1.5 text-xs">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: s.style.stroke }}
            />
            <span className={s.main ? "font-semibold" : "text-muted-foreground"}>
              {s.name}
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}
