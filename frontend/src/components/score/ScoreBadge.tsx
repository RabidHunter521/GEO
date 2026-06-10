// frontend/src/components/score/ScoreBadge.tsx
import { Badge } from "@/components/ui/badge"
import { getScoreBand } from "@/lib/score-utils"
import { cn } from "@/lib/utils"

interface Props {
  score: number | null
  className?: string
}

const BAND_CLASS: Record<string, string> = {
  green: "bg-score-strong-bg text-score-strong border-score-strong/25",
  yellow: "bg-score-watch-bg text-score-watch border-score-watch/30",
  red: "bg-score-low-bg text-score-low border-score-low/25",
}

export function ScoreBadge({ score, className }: Props) {
  if (score === null) {
    return (
      <Badge variant="outline" className={cn("text-muted-foreground", className)}>
        —
      </Badge>
    )
  }

  const band = getScoreBand(score)

  return (
    <Badge
      variant="outline"
      className={cn("font-semibold tabular-nums", BAND_CLASS[band.color], className)}
    >
      {score.toFixed(0)}
    </Badge>
  )
}
