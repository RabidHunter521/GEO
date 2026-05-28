"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { signOut } from "next-auth/react"
import {
  LayoutDashboard,
  Search,
  BarChart3,
  Wrench,
  FileText,
  Activity,
  Settings,
  Users,
  LogOut,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

const CLIENT_NAV = [
  { href: "",             label: "Overview",                icon: LayoutDashboard },
  { href: "/scan",        label: "Scan & Visibility",       icon: Search },
  { href: "/competitors", label: "Competitor Intelligence", icon: BarChart3 },
  { href: "/toolkit",     label: "AI Readiness Toolkit",   icon: Wrench },
  { href: "/reports",     label: "Reports",                icon: FileText },
  { href: "/activity",    label: "Activity Log",           icon: Activity },
  { href: "/settings",    label: "Settings",               icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()
  // Extract client ID from /clients/<uuid>/... pattern
  const clientMatch = pathname.match(/^\/clients\/([^/]+)/)
  const clientId = clientMatch?.[1]

  function isActive(href: string) {
    return pathname === href || pathname.startsWith(href + "/")
  }

  return (
    <aside className="w-60 border-r bg-background flex flex-col h-screen sticky top-0 shrink-0">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b">
        <Link href="/clients" className="font-semibold text-base tracking-tight">
          SeenBy
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-1">
        <Link
          href="/clients"
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors",
            isActive("/clients") && !clientId
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
          )}
        >
          <Users className="h-4 w-4" />
          All Clients
        </Link>

        {clientId && (
          <>
            <Separator className="my-2" />
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
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
                    active
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </Link>
              )
            })}
          </>
        )}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-muted-foreground hover:text-foreground gap-2"
          onClick={() => signOut({ callbackUrl: "/auth/login" })}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </aside>
  )
}
