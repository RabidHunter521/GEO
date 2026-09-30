// frontend/src/components/score/ScoreBadge.tsx
import { Badge } from "@/components/ui/badge"
import { getScoreBand, getScoreColor } from "@/lib/score-utils"
import { cn } from "@/lib/utils"

interface Props {
  score: number | null
  className?: string
  /** Show the band name ("Good") beside the number, so the score never
   *  relies on colour alone. Screen readers always get the band. */
  showBand?: boolean
}

const BAND_CLASS: Record<string, string> = {
  green: "bg-score-strong-bg text-score-strong border-score-strong/25",
  yellow: "bg-score-watch-bg text-score-watch-fg border-score-watch/30",
  red: "bg-score-low-bg text-score-low-fg border-score-low/25",
}

export function ScoreBadge({ score, className, showBand = false }: Props) {
  if (score === null) {
    return (
      <Badge variant="outline" className={cn("text-muted-foreground", className)}>
        —
      </Badge>
    )
  }

  const band = getScoreBand(score).name
  const bandLabel = band.charAt(0).toUpperCase() + band.slice(1)
  return (
    <Badge
      variant="outline"
      className={cn("font-semibold tabular-nums", BAND_CLASS[getScoreColor(score)], className)}
      aria-label={`${score.toFixed(0)} out of 100, ${bandLabel}`}
    >
      {score.toFixed(0)}
      {showBand && <span className="ml-1 font-medium">· {bandLabel}</span>}
    </Badge>
  )
}
