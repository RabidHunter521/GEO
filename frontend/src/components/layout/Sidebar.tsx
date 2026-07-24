"use client"

import { useState } from "react"
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
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const CLIENT_NAV = [
  { href: "",             label: "Overview",                icon: LayoutDashboard },
  { href: "/checklist",   label: "Checklist",               icon: ListChecks },
  { href: "/scan",        label: "Scan & Visibility",       icon: Search },
  { href: "/competitors", label: "Competitor Intelligence", icon: BarChart3 },
  { href: "/toolkit",     label: "AI Readiness Toolkit",   icon: Wrench },
  { href: "/content-gaps", label: "Content Gaps",          icon: Target },
  { href: "/content-roadmap", label: "Content Roadmap",    icon: Map },
  { href: "/content-studio", label: "Content Studio",      icon: PenTool },
  { href: "/authority",  label: "Authority & Presence", icon: Award },
  { href: "/reports",     label: "Reports",                icon: FileText },
  { href: "/activity",    label: "Activity Log",           icon: Activity },
  { href: "/settings",    label: "Settings",               icon: Settings },
]

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

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  // Static sibling routes under /clients that are NOT a client id — they must not
  // trigger the per-client nav block (otherwise it renders links like
  // /clients/gap-matrix/scan).
  const RESERVED_CLIENT_ROUTES = new Set(["gap-matrix"])
  const clientMatch = pathname.match(/^\/clients\/([^/]+)/)
  const rawClientId = clientMatch?.[1]
  const clientId = rawClientId && !RESERVED_CLIENT_ROUTES.has(rawClientId) ? rawClientId : undefined

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

  const allClientsActive = pathname === "/clients" && !clientId
  const gapActive = pathname === "/clients/gap-matrix"

  return (
    <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
      <Link href="/clients" onClick={onNavigate} className={linkClass(allClientsActive)}>
        {activeBar(allClientsActive)}
        <Users className={cn("h-4 w-4 shrink-0", allClientsActive ? "text-primary" : "")} />
        All Clients
      </Link>
      <Link href="/clients/gap-matrix" onClick={onNavigate} className={linkClass(gapActive)}>
        {activeBar(gapActive)}
        <Table2 className={cn("h-4 w-4 shrink-0", gapActive ? "text-primary" : "")} />
        Gap Matrix
      </Link>

      {clientId && (
        <div className="pt-5">
          <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50">
            Client
          </p>
          {CLIENT_NAV.map((item) => {
            const href = `/clients/${clientId}${item.href}`
            const active =
              item.href === ""
                ? pathname === `/clients/${clientId}`
                : pathname.startsWith(href)
            return (
              <Link
                key={item.href}
                href={href}
                onClick={onNavigate}
                className={linkClass(active)}
              >
                {activeBar(active)}
                <item.icon
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
export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-bg))] backdrop-blur md:flex">
      {/* Subtle top gradient wash echoing brand */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-primary/[0.04] to-transparent" />
      <div className="relative flex h-16 items-center border-b border-[hsl(var(--sidebar-border))] px-5">
        <Brand />
      </div>
      <NavLinks />
      <SignOutButton />
    </aside>
  )
}

/** Mobile top bar + slide-over drawer — visible only on small screens */
export function MobileSidebar() {
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
              <NavLinks onNavigate={() => setOpen(false)} />
              <SignOutButton />
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>
      </header>
    </div>
  )
}
