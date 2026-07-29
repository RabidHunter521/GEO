"use client"

import { useState } from "react"
import type { ComponentType } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { signOut } from "next-auth/react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import {
  LayoutDashboard,
  ListChecks,
  Search,
  BarChart3,
  Wrench,
  Target,
  Map,
  PenTool,
  FileText,
  Activity,
  Settings,
  Users,
  Table2,
  LogOut,
  Eye,
  Menu,
  X,
  Award,
  Inbox,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { ADMIN_GLOBAL_NAV, CLIENT_NAV_GROUPS, isNavItemActive } from "@/lib/navigation"

type IconType = ComponentType<{ className?: string }>

/** Icon for the ungrouped Overview item — not part of navigation.ts, which stays serializable. */
const OVERVIEW_ICON: IconType = LayoutDashboard

/** Icons for the three global (non-client-scoped) destinations, keyed by href. */
const GLOBAL_NAV_ICONS: Record<string, IconType> = {
  "/clients": Users,
  "/gap-matrix": Table2,
  "/review-queue": Inbox,
}

/** Icons for client-scoped sub-routes, keyed by the relative href used in CLIENT_NAV_GROUPS. */
const CLIENT_NAV_ICONS: Record<string, IconType> = {
  "/scan": Search,
  "/competitors": BarChart3,
  "/toolkit": Wrench,
  "/authority": Award,
  "/content-gaps": Target,
  "/content-roadmap": Map,
  "/content-studio": PenTool,
  "/checklist": ListChecks,
  "/activity": Activity,
  "/reports": FileText,
  "/settings": Settings,
}

function Brand() {
  return (
    <Link href="/clients" className="group flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-violet-700 text-primary-foreground shadow-brand transition-shadow group-hover:shadow-brand-lg">
        <Eye className="h-4 w-4" />
      </span>
      <span className="font-display text-lg font-semibold tracking-tight text-foreground">
        Seen<span className="text-primary">By</span>
      </span>
    </Link>
  )
}

function NavLinks({
  onNavigate, suggestedCount = 0,
}: { onNavigate?: () => void; suggestedCount?: number }) {
  const pathname = usePathname()
  const clientMatch = pathname.match(/^\/clients\/([^/]+)/)
  const clientId = clientMatch?.[1]

  const linkClass = (active: boolean) =>
    cn(
      "relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150",
      active
        ? "bg-gradient-to-r from-primary/12 to-primary/6 text-primary shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.15)]"
        : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
    )

  const activeBar = (active: boolean) =>
    active ? (
      <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary" />
    ) : null

  return (
    <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
      {ADMIN_GLOBAL_NAV.map((item) => {
        const active =
          item.href === "/clients" ? pathname === "/clients" && !clientId : pathname === item.href
        const Icon = GLOBAL_NAV_ICONS[item.href]
        return (
          <Link key={item.href} href={item.href} onClick={onNavigate} className={linkClass(active)}>
            {activeBar(active)}
            <Icon className={cn("h-4 w-4 shrink-0", active ? "text-primary" : "")} />
            {item.label}
            {item.href === "/review-queue" && suggestedCount > 0 && (
              <span className="ml-auto rounded-full bg-primary px-2 py-0.5 text-[10px] font-bold text-primary-foreground">
                {suggestedCount}
              </span>
            )}
          </Link>
        )
      })}

      {clientId && (
        <div className="pt-5">
          <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50">
            Client
          </p>
          <Link
            href={`/clients/${clientId}`}
            onClick={onNavigate}
            className={linkClass(isNavItemActive(pathname, clientId, ""))}
          >
            {activeBar(isNavItemActive(pathname, clientId, ""))}
            <OVERVIEW_ICON
              className={cn(
                "h-4 w-4 shrink-0 transition-colors",
                isNavItemActive(pathname, clientId, "") ? "text-primary" : "",
              )}
            />
            Overview
          </Link>

          {CLIENT_NAV_GROUPS.map((group) => (
            <div key={group.label} className="pt-4">
              <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/40">
                {group.label}
              </p>
              {group.items.map((item) => {
                const href = `/clients/${clientId}${item.href}`
                const active = isNavItemActive(pathname, clientId, item.href)
                const Icon = CLIENT_NAV_ICONS[item.href]
                return (
                  <Link
                    key={item.href}
                    href={href}
                    onClick={onNavigate}
                    className={linkClass(active)}
                  >
                    {activeBar(active)}
                    <Icon
                      className={cn(
                        "h-4 w-4 shrink-0 transition-colors",
                        active ? "text-primary" : "",
                      )}
                    />
                    {item.label}
                  </Link>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </nav>
  )
}

function SignOutButton() {
  return (
    <div className="border-t border-border/60 p-3">
      <Button
        variant="ghost"
        size="sm"
        className="w-full justify-start gap-2 text-muted-foreground hover:bg-destructive/8 hover:text-foreground"
        onClick={() => signOut({ callbackUrl: "/auth/login" })}
      >
        <LogOut className="h-4 w-4" />
        Sign out
      </Button>
    </div>
  )
}

/** Desktop rail — hidden on small screens */
export function Sidebar({ suggestedCount }: { suggestedCount?: number }) {
  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-bg))] backdrop-blur md:flex">
      {/* Subtle top gradient wash echoing brand */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-primary/[0.04] to-transparent" />
      <div className="relative flex h-16 items-center border-b border-[hsl(var(--sidebar-border))] px-5">
        <Brand />
      </div>
      <NavLinks suggestedCount={suggestedCount} />
      <SignOutButton />
    </aside>
  )
}

/** Mobile top bar + slide-over drawer — visible only on small screens */
export function MobileSidebar({ suggestedCount }: { suggestedCount?: number }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="md:hidden">
      <header className="flex h-14 items-center justify-between border-b bg-[hsl(var(--sidebar-bg))]/90 px-4 backdrop-blur">
        <Brand />
        <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
          <DialogPrimitive.Trigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open menu">
              <Menu className="h-5 w-5" />
            </Button>
          </DialogPrimitive.Trigger>
          <DialogPrimitive.Portal>
            <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-foreground/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
            <DialogPrimitive.Content className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-[hsl(var(--sidebar-bg))] shadow-xl duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left">
              <DialogPrimitive.Title className="sr-only">Navigation</DialogPrimitive.Title>
              <div className="flex h-14 items-center justify-between border-b border-[hsl(var(--sidebar-border))] px-4">
                <Brand />
                <DialogPrimitive.Close asChild>
                  <Button variant="ghost" size="icon" aria-label="Close menu">
                    <X className="h-5 w-5" />
                  </Button>
                </DialogPrimitive.Close>
              </div>
              <NavLinks onNavigate={() => setOpen(false)} suggestedCount={suggestedCount} />
              <SignOutButton />
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>
      </header>
    </div>
  )
}
