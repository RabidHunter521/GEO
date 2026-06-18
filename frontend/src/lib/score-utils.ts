// frontend/src/lib/score-utils.ts
import type { ScoreBand } from "@/types"

const SCORE_BANDS: Array<ScoreBand & { min: number; max: number }> = [
  { name: "excellent",  min: 80, max: 100, color: "green"  },
  { name: "good",       min: 65, max: 79,  color: "green"  },
  { name: "fair",       min: 50, max: 64,  color: "yellow" },
  { name: "developing", min: 35, max: 49,  color: "yellow" },
  { name: "low",        min: 0,  max: 34,  color: "red"    },
]

export function getScoreBand(score: number): ScoreBand & { min: number; max: number } {
  // Bands are ordered best→worst, so the first band whose `min` the score
  // clears is the correct one. Matching on `min` alone (not `<= max`) avoids
  // dropping a fractional score like 79.5 — which clears no band's integer
  // `max` — through to the "low" fallback.
  return SCORE_BANDS.find((b) => score >= b.min) ?? SCORE_BANDS[4]
}

// Score color is a simple 3-band traffic-light, independent of the named
// bands above (which still drive labels). Thresholds: 0–29 red, 30–69 yellow,
// 70–100 green.
export type ScoreColor = "red" | "yellow" | "green"

export function getScoreColor(score: number): ScoreColor {
  if (score >= 70) return "green"
  if (score >= 30) return "yellow"
  return "red"
}

// Band names best-to-worst, for filter dropdowns etc.
export const SCORE_BAND_NAMES: ScoreBand["name"][] = SCORE_BANDS.map((b) => b.name)
