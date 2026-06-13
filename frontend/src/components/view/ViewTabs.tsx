"use client"

// frontend/src/components/view/ViewTabs.tsx
// Horizontal tab navigation for the read-only client view.
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"

const BASE_TABS = [
  { segment: "", label: "Overview" },
  { segment: "/scan", label: "Scan & Visibility" },
  { segment: "/competitors", label: "Competitors" },
] as const

const REPORTS_TAB = { segment: "/reports", label: "Reports" } as const

interface Props {
  token: string
  showOurWork?: boolean
  showContentPlan?: boolean
}

export function ViewTabs({ token, showOurWork, showContentPlan }: Props) {
  const pathname = usePathname()
  const base = `/view/${token}`

  // Deliverable tabs only appear once they have content (set by the overview).
  const tabs = [
    ...BASE_TABS,
    ...(showOurWork ? [{ segment: "/our-work", label: "Our Work" }] : []),
    ...(showContentPlan ? [{ segment: "/content-plan", label: "Content Plan" }] : []),
    REPORTS_TAB,
  ]

  return (
    <nav className="-mb-px flex gap-1 overflow-x-auto" aria-label="Sections">
      {tabs.map((tab) => {
        const href = `${base}${tab.segment}`
        const active =
          tab.segment === "" ? pathname === base : pathname.startsWith(href)
        return (
          <Link
            key={tab.label}
            href={href}
            className={cn(
              "whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors",
              active
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
            )}
          >
            {tab.label}
          </Link>
        )
      })}
    </nav>
  )
}
