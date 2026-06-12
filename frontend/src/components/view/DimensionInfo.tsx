// frontend/src/components/view/DimensionInfo.tsx
// Clickable dimension label in the score breakdown — toggles an inline,
// plain-English description of what the dimension measures. Inline
// (rather than a floating popover) so it never overlaps neighboring cards
// in the 2-column grid.
"use client"

import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

interface Props {
  label: string
  description: string
}

export function DimensionInfo({ label, description }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-left text-sm font-medium transition-colors hover:text-primary"
      >
        {label}
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}
    </div>
  )
}
