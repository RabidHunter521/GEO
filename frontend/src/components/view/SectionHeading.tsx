// frontend/src/components/view/SectionHeading.tsx
// Shared section header for the read-only client view. A short violet accent
// bar differentiates each section so a long scroll reads as a sequence of
// chapters rather than one flat wall of grey labels. Optional trailing action
// (e.g. a "see the full plan" link).
import type { ReactNode } from "react"

interface Props {
  children: ReactNode
  /** Optional leading icon (e.g. a lucide glyph already sized/colored). */
  icon?: ReactNode
  /** Optional trailing element, right-aligned (link, badge, etc.). */
  action?: ReactNode
}

export function SectionHeading({ children, icon, action }: Props) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        <span
          aria-hidden
          className="h-3.5 w-1 shrink-0 rounded-full bg-primary/70"
        />
        {icon}
        {children}
      </h2>
      {action}
    </div>
  )
}
