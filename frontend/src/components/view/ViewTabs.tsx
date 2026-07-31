"use client"

// frontend/src/components/view/ViewTabs.tsx
// Navigation for the read-only client view: six outcome destinations at `sm`
// and above (horizontal tabs), a native <select> below `sm`.
//
// Competitors is deliberately not one of the six — it's evidence linked from
// Visibility and Overview rather than a primary destination — but the route
// stays live for existing links, so neither nav here claims to be "active"
// when the client is actually on /competitors.
import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { cn } from "@/lib/utils"

const OVERVIEW_TAB = { segment: "", label: "Overview" } as const
const SCAN_TAB = { segment: "/scan", label: "Visibility" } as const
const REPUTATION_TAB = { segment: "/reputation", label: "Reputation" } as const
const CONTENT_PLAN_TAB = { segment: "/content-plan", label: "Action Plan" } as const
const PROGRESS_TAB = { segment: "/progress", label: "Progress" } as const
const REPORTS_TAB = { segment: "/reports", label: "Reports" } as const

interface Props {
  token: string
  showContentPlan?: boolean
  showProgress?: boolean
  isProspect?: boolean
}

export function ViewTabs({ token, showContentPlan, showProgress, isProspect }: Props) {
  const pathname = usePathname()
  const router = useRouter()
  const base = `/view/${token}`

  // On narrow screens the tab row can overflow horizontally (e.g. Reports
  // scrolled off-screen). Show edge fades so it's obvious there's more to see.
  const scrollRef = useRef<HTMLDivElement>(null)
  const [edges, setEdges] = useState({ left: false, right: false })

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const update = () => {
      setEdges({
        left: el.scrollLeft > 1,
        right: el.scrollLeft + el.clientWidth < el.scrollWidth - 1,
      })
    }
    update()
    el.addEventListener("scroll", update, { passive: true })
    window.addEventListener("resize", update)
    return () => {
      el.removeEventListener("scroll", update)
      window.removeEventListener("resize", update)
    }
  }, [])

  // Prospects get a deliberately simple view: Overview + Visibility only.
  // Everything else (Reputation, Action Plan, Progress, Reports, Competitors)
  // is reserved for converted clients. "Our Work" is intentionally
  // admin-only and never surfaced to clients.
  const tabs = isProspect
    ? [OVERVIEW_TAB, SCAN_TAB]
    : [
        OVERVIEW_TAB,
        SCAN_TAB,
        REPUTATION_TAB,
        ...(showContentPlan ? [CONTENT_PLAN_TAB] : []),
        ...(showProgress ? [PROGRESS_TAB] : []),
        REPORTS_TAB,
      ]

  const isActive = (tab: (typeof tabs)[number]) => {
    const href = `${base}${tab.segment}`
    return tab.segment === "" ? pathname === base : pathname.startsWith(href)
  }
  // Undefined when the client is on a page outside the six destinations
  // (e.g. /competitors) — the select falls back to its first option in that
  // case, same as an unmatched native <select> always does.
  const activeTab = tabs.find(isActive)

  return (
    <div className="relative">
      {/* Below `sm`: a real, labelled <select> instead of the horizontal tab
          bar, which clips on narrow screens (e.g. Reports scrolled
          off-screen). */}
      <div className="sm:hidden">
        <label htmlFor="view-section-select" className="sr-only">
          Jump to section
        </label>
        <select
          id="view-section-select"
          value={activeTab ? `${base}${activeTab.segment}` : `${base}${tabs[0].segment}`}
          onChange={(e) => router.push(e.target.value)}
          className="h-11 w-full rounded-md border border-input bg-card px-3 text-sm font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
        >
          {tabs.map((tab) => (
            <option key={tab.label} value={`${base}${tab.segment}`}>
              {tab.label}
            </option>
          ))}
        </select>
      </div>

      <nav
        ref={scrollRef}
        className="no-scrollbar -mb-px hidden gap-1 overflow-x-auto sm:flex"
        aria-label="Sections"
      >
        {tabs.map((tab) => {
          const href = `${base}${tab.segment}`
          const active = isActive(tab)
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
      {edges.left && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 left-0 hidden w-8 bg-gradient-to-r from-card to-transparent sm:block"
        />
      )}
      {edges.right && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 right-0 hidden w-8 bg-gradient-to-l from-card to-transparent sm:block"
        />
      )}
    </div>
  )
}
