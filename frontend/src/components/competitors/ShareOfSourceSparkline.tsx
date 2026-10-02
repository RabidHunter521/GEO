import type { ShareOfSourceHistoryPoint } from "@/types"
import { currentBaseline } from "@/lib/share-of-source-trend"

const WIDTH = 240
const HEIGHT = 48
const PAD = 4

export function ShareOfSourceSparkline({ points }: { points: ShareOfSourceHistoryPoint[] }) {
  if (points.length < 2) {
    return (
      <p className="text-xs text-muted-foreground">
        Trend appears after your next scan — need at least two data points.
      </p>
    )
  }

  const values = points.map((p) => p.client_share_pct)
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const stepX = (WIDTH - PAD * 2) / (points.length - 1)

  const coords = values.map((v, i) => {
    const x = PAD + i * stepX
    const y = PAD + (1 - (v - min) / range) * (HEIGHT - PAD * 2)
    return `${x},${y}`
  })

  // The trend is read only within the latest source pool: a coverage change
  // (more or fewer platforms, or a changed method) is a new baseline.
  const baseline = currentBaseline(points)
  const breakIndex = points.length - baseline.length
  const breakX = breakIndex > 0 ? PAD + breakIndex * stepX : null

  const first = baseline[0].client_share_pct
  const last = values[values.length - 1]
  const delta = last - first
  const trendLabel =
    baseline.length < 2
      ? "new baseline: source tracking changed"
      : delta > 0.5 ? `+${delta.toFixed(1)}pt` : delta < -0.5 ? `${delta.toFixed(1)}pt` : "flat"
  const trendColor =
    baseline.length < 2
      ? "text-muted-foreground"
      : delta > 0.5 ? "text-score-good" : delta < -0.5 ? "text-score-critical" : "text-muted-foreground"
  const trendSuffix = baseline.length < 2 ? "" : ` vs ${baseline.length - 1} scans ago`

  return (
    <div className="flex items-center gap-3">
      <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="shrink-0">
        <polyline
          points={coords.join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className="text-primary"
        />
        {breakX !== null && (
          <line
            x1={breakX}
            x2={breakX}
            y1={0}
            y2={HEIGHT}
            stroke="currentColor"
            strokeDasharray="2 2"
            className="text-muted-foreground"
          >
            <title>Source tracking changed here: trend restarts from this scan</title>
          </line>
        )}
      </svg>
      <div className="text-xs">
        <div className="font-medium tabular-nums">{last.toFixed(0)}% now</div>
        <div className={`tabular-nums ${trendColor}`}>{trendLabel}{trendSuffix}</div>
      </div>
    </div>
  )
}
