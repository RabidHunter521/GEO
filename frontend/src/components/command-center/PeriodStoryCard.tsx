// frontend/src/components/command-center/PeriodStoryCard.tsx
// Plain restatement of stored numbers for the current period — no forecasts,
// no interpretation beyond what command_center_service.py already computed.
import type { PeriodStory } from "@/types"

interface Props {
  story: PeriodStory
}

export function PeriodStoryCard({ story }: Props) {
  return (
    <div className="rounded-lg border bg-card p-5">
      <p className="font-display text-lg font-semibold text-foreground text-balance">
        {story.headline}
      </p>
      {story.bullets.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {story.bullets.map((bullet, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground leading-relaxed">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/50" />
              {bullet}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
