import type { ShareOfSourceHistoryPoint } from "@/types"

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

  const first = values[0]
  const last = values[values.length - 1]
  const delta = last - first
  const trendLabel =
    delta > 0.5 ? `+${delta.toFixed(1)}pt` : delta < -0.5 ? `${delta.toFixed(1)}pt` : "flat"
  const trendColor = delta > 0.5 ? "text-score-good" : delta < -0.5 ? "text-score-critical" : "text-muted-foreground"

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
      </svg>
      <div className="text-xs">
        <div className="font-medium tabular-nums">{last.toFixed(0)}% now</div>
        <div className={`tabular-nums ${trendColor}`}>{trendLabel} vs {points.length - 1} scans ago</div>
      </div>
    </div>
  )
}
