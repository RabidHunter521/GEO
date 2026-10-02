import type { ShareOfSourceHistoryPoint } from "@/types"

/**
 * The points measured on the same source pool as the latest one.
 *
 * A point with `coverage_changed` starts a new baseline (more AI platforms
 * tracked, or a changed capture method), so a trend may only be read from
 * that point onward — the move into it is coverage, not the client's standing.
 */
export function currentBaseline(points: ShareOfSourceHistoryPoint[]): ShareOfSourceHistoryPoint[] {
  let start = 0
  points.forEach((p, i) => {
    if (p.coverage_changed) start = i
  })
  return points.slice(start)
}
