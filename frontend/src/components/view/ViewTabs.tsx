"use client"

// frontend/src/components/view/ViewTabs.tsx
// Horizontal tab navigation for the read-only client view.
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"

const OVERVIEW_TAB = { segment: "", label: "Overview" } as const
const SCAN_TAB = { segment: "/scan", label: "Scan & Visibility" } as const
const COMPETITORS_TAB = { segment: "/competitors", label: "Competitors" } as const
const REPORTS_TAB = { segment: "/reports", label: "Reports" } as const

interface Props {
  token: string
  showContentPlan?: boolean
  isProspect?: boolean
}

export function ViewTabs({ token, showContentPlan, isProspect }: Props) {
  const pathname = usePathname()
  const base = `/view/${token}`

  // Prospects get a deliberately simple view: Overview + Scan only. Everything
  // else (competitors, content plan, reports) is reserved for converted clients.
  // "Our Work" is intentionally admin-only and never surfaced to clients.
  const tabs = isProspect
    ? [OVERVIEW_TAB, SCAN_TAB]
    : [
        OVERVIEW_TAB,
        SCAN_TAB,
        COMPETITORS_TAB,
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
