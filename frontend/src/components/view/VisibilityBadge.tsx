// frontend/src/components/view/VisibilityBadge.tsx
// Client-facing visibility status. Language rules: only ever
// "Seen by AI" / "Not yet seen by AI" — never "cited" or "mentioned".
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface Props {
  seen: boolean
  className?: string
}

export function VisibilityBadge({ seen, className }: Props) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "whitespace-nowrap font-medium",
        seen
          ? "bg-score-strong-bg text-score-strong border-score-strong/25"
          : "bg-muted text-muted-foreground border-border",
        className,
      )}
    >
      {seen ? "Seen by AI" : "Not yet seen by AI"}
    </Badge>
  )
}
