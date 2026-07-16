"use client"

// frontend/src/components/view/ViewTabs.tsx
// Horizontal tab navigation for the read-only client view.
import { useEffect, useRef, useState } from "react"
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
    <div className="relative">
      <nav
        ref={scrollRef}
        className="no-scrollbar -mb-px flex gap-1 overflow-x-auto"
        aria-label="Sections"
      >
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
      {edges.left && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-card to-transparent"
        />
      )}
      {edges.right && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-card to-transparent"
        />
      )}
    </div>
  )
}
