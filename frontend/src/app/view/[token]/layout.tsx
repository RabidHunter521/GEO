// frontend/src/app/view/[token]/layout.tsx
// Read-only client view shell. No admin session — the share token in the
// URL is the credential. Tokenized pages must never be indexed or cached.
import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { ExternalLink } from "lucide-react"
import { getViewOverview } from "@/lib/view-api"
import { ViewTabs } from "@/components/view/ViewTabs"

export const dynamic = "force-dynamic"

export const metadata: Metadata = {
  title: "Your AI Visibility — SeenBy",
  robots: { index: false, follow: false },
}

export default async function ClientViewLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const overview = await getViewOverview(token)

  // Invalid / revoked / archived token → a real 404, rendered by not-found.tsx
  // (which shows LinkInactive). Matches the page-level notFound() so the status
  // code is uniform, per the spec's "uniform 404" requirement.
  if (!overview) {
    notFound()
  }

  const { profile } = overview
  const host = profile.website?.replace(/^https?:\/\//, "").replace(/\/$/, "")

  return (
    <div className="min-h-screen bg-app-wash">
      <header className="border-b bg-card">
        <div className="mx-auto max-w-[1400px] px-4 pt-6 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-4">
            <div className="flex min-w-0 items-center gap-4">
              {profile.logo_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={profile.logo_url}
                  alt={`${profile.name} logo`}
                  className="h-12 w-12 shrink-0 rounded-lg border bg-card object-contain p-1"
                />
              )}
              <div className="min-w-0">
              <p className="font-display text-lg font-bold tracking-tight text-primary">
                SeenBy
              </p>
              <h1 className="mt-1 truncate font-display text-2xl font-semibold tracking-tight">
                {profile.name}
              </h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                {profile.website && (
                  <a
                    href={profile.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-0.5 text-secondary-foreground transition-colors hover:bg-secondary/70"
                  >
                    {host}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                {profile.industry && (
                  <span className="rounded-full bg-muted px-2.5 py-0.5">
                    {profile.industry}
                  </span>
                )}
              </div>
              </div>
            </div>
          </div>
          <ViewTabs
            token={token}
            showContentPlan={overview.has_content_plan}
            isProspect={profile.is_prospect}
          />
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">{children}</main>

      <footer className="border-t py-6">
        <p className="text-center text-xs text-muted-foreground">
          Powered by{" "}
          <a
            href="https://seenby.my"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            SeenBy
          </a>{" "}
          — AI visibility tracking
        </p>
      </footer>
    </div>
  )
}
