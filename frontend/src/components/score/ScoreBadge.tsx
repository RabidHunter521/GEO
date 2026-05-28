// frontend/src/components/score/ScoreBadge.tsx
import { Badge } from "@/components/ui/badge"
import { getScoreBand } from "@/lib/score-utils"
import { cn } from "@/lib/utils"

interface Props {
  score: number | null
  className?: string
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
  const colorClass =
    band.color === "green"
      ? "bg-green-100 text-green-800 border-green-200"
      : band.color === "yellow"
        ? "bg-yellow-100 text-yellow-800 border-yellow-200"
        : "bg-red-100 text-red-800 border-red-200"

  return (
    <Badge
      variant="outline"
      className={cn("font-semibold", colorClass, className)}
    >
      {score.toFixed(0)}
    </Badge>
  )
}
