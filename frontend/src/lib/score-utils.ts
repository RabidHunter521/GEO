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
  return (
    SCORE_BANDS.find((b) => score >= b.min && score <= b.max) ?? SCORE_BANDS[4]
  )
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
