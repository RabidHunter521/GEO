"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { signOut } from "next-auth/react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import {
  LayoutDashboard,
  Search,
  BarChart3,
  Wrench,
  Target,
  Map,
  FileText,
  Activity,
  Settings,
  Users,
  LogOut,
  Eye,
  Menu,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const CLIENT_NAV = [
  { href: "",             label: "Overview",                icon: LayoutDashboard },
  { href: "/scan",        label: "Scan & Visibility",       icon: Search },
  { href: "/competitors", label: "Competitor Intelligence", icon: BarChart3 },
  { href: "/toolkit",     label: "AI Readiness Toolkit",   icon: Wrench },
  { href: "/content-gaps", label: "Content Gaps",          icon: Target },
  { href: "/content-roadmap", label: "Content Roadmap",    icon: Map },
  { href: "/reports",     label: "Reports",                icon: FileText },
  { href: "/activity",    label: "Activity Log",           icon: Activity },
  { href: "/settings",    label: "Settings",               icon: Settings },
]

function Brand() {
  return (
    <Link href="/clients" className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-brand">
        <Eye className="h-4 w-4" />
      </span>
      <span className="font-display text-lg font-semibold tracking-tight">
        SeenBy
      </span>
    </Link>
  )
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  const clientMatch = pathname.match(/^\/clients\/([^/]+)/)
  const clientId = clientMatch?.[1]

  const linkClass = (active: boolean) =>
    cn(
      "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
      active
        ? "bg-accent font-medium text-accent-foreground"
        : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
    )

  const activeBar = (active: boolean) =>
    active ? (
      <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-primary" />
    ) : null

  const allClientsActive = pathname === "/clients" && !clientId

  return (
    <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
      <Link href="/clients" onClick={onNavigate} className={linkClass(allClientsActive)}>
        {activeBar(allClientsActive)}
        <Users className="h-4 w-4 shrink-0" />
        All Clients
      </Link>

      {clientId && (
        <div className="pt-4">
          <p className="px-3 pb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
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
                    "h-4 w-4 shrink-0",
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
    <div className="border-t p-3">
      <Button
        variant="ghost"
        size="sm"
        className="w-full justify-start gap-2 text-muted-foreground hover:text-foreground"
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
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r bg-card/60 backdrop-blur md:flex">
      <div className="flex h-16 items-center border-b px-5">
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
      <header className="flex h-14 items-center justify-between border-b bg-card/80 px-4 backdrop-blur">
        <Brand />
        <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
          <DialogPrimitive.Trigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open menu">
              <Menu className="h-5 w-5" />
            </Button>
          </DialogPrimitive.Trigger>
          <DialogPrimitive.Portal>
            <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-foreground/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
            <DialogPrimitive.Content className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-card shadow-xl duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left">
              <DialogPrimitive.Title className="sr-only">Navigation</DialogPrimitive.Title>
              <div className="flex h-14 items-center justify-between border-b px-4">
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
