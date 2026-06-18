// frontend/src/app/clients/[id]/layout.tsx
import { notFound } from "next/navigation"
import { ExternalLink } from "lucide-react"
import { getClient } from "@/lib/api"

function initials(name: string | null | undefined) {
  return (name ?? "")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("")
}

export default async function ClientLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  let client
  try {
    client = await getClient(id)
  } catch {
    notFound()
  }
  if (!client) notFound()

  const host = client.website?.replace(/^https?:\/\//, "").replace(/\/$/, "")

  return (
    <div>
      <div className="mb-6 flex items-center gap-4 border-b pb-5">
        {client.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={client.logo_url}
            alt={`${client.name} logo`}
            className="h-12 w-12 shrink-0 rounded-xl border bg-card object-contain p-1"
          />
        ) : (
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 font-display text-lg font-semibold text-primary">
            {initials(client.name)}
          </span>
        )}
        <div className="min-w-0">
          <h1 className="truncate font-display text-2xl font-semibold tracking-tight">
            {client.name}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {client.website && (
              <a
                href={client.website}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-0.5 text-secondary-foreground transition-colors hover:bg-secondary/70"
              >
                {host}
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
            {client.industry && (
              <span className="rounded-full bg-muted px-2.5 py-0.5">
                {client.industry}
              </span>
            )}
            {client.share_token && (
              <a
                href={`/view/${client.share_token}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-0.5 font-medium text-primary transition-colors hover:bg-primary/20"
                title="Preview what this client sees"
              >
                Client view
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        </div>
      </div>
      {children}
    </div>
  )
}
