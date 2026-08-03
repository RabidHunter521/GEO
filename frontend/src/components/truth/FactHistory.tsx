import { ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { TruthFact } from "@/types"

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Not set"
}

function statusVariant(status: string): "default" | "secondary" | "outline" {
  if (status === "approved") return "default"
  if (status === "draft") return "secondary"
  return "outline"
}

export function FactHistory({ fact }: { fact: TruthFact }) {
  return (
    <Card>
      <CardHeader className="py-4">
        <CardTitle className="text-base">History · {fact.fact_key}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {fact.versions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No versions have been recorded yet.</p>
        ) : fact.versions.map((version) => (
          <div key={version.id} className="rounded-md border p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={statusVariant(version.status)}>{version.status}</Badge>
              <span className="font-medium">{version.value.display_value}</span>
            </div>
            <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-2">
              <div><dt className="inline font-medium text-foreground">Effective from: </dt><dd className="inline">{dateTime(version.effective_from)}</dd></div>
              <div><dt className="inline font-medium text-foreground">Effective to: </dt><dd className="inline">{dateTime(version.effective_to)}</dd></div>
              <div><dt className="inline font-medium text-foreground">Created: </dt><dd className="inline">{dateTime(version.created_at)}</dd></div>
              <div><dt className="inline font-medium text-foreground">Approved: </dt><dd className="inline">{version.approved_by ? `${version.approved_by} · ${dateTime(version.approved_at)}` : "Awaiting approval"}</dd></div>
            </dl>
            {version.source_url && <a className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline" href={version.source_url} target="_blank" rel="noreferrer">View source <ExternalLink className="h-3 w-3" /></a>}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
