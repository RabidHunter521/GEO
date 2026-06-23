// frontend/src/app/view/[token]/reports/page.tsx
// Read-only list of delivered monthly reports with PDF downloads.
import { notFound } from "next/navigation"
import { FileText, Download } from "lucide-react"
import { getViewReports } from "@/lib/view-api"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import { SectionHeading } from "@/components/view/SectionHeading"

function formatPeriod(start: string, end: string): string {
  const opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }
  return `${new Date(start).toLocaleDateString("en-MY", opts)} — ${new Date(end).toLocaleDateString("en-MY", opts)}`
}

export default async function ViewReportsPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const reports = await getViewReports(token)
  if (!reports) notFound()

  if (reports.length === 0) {
    return (
      <div className="reveal relative overflow-hidden rounded-2xl border bg-card bg-hero-wash p-8 text-center shadow-brand-lg">
        <span
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <FileText className="h-6 w-6" />
          </span>
          <p className="mt-4 font-display text-lg font-semibold">No reports yet</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Your first monthly visibility report will appear here once it&apos;s
            been delivered by the SeenBy team.
          </p>
        </div>
      </div>
    )
  }

  const [latest, ...older] = reports

  return (
    <div className="space-y-6">
      {/* Latest report — highlighted hero */}
      <section className="reveal" style={{ animationDelay: "0ms" }}>
        <SectionHeading>Latest Report</SectionHeading>
        <div className="relative flex flex-col gap-4 overflow-hidden rounded-2xl border bg-card bg-hero-wash p-6 shadow-brand-lg sm:flex-row sm:items-center sm:justify-between">
          <span
            aria-hidden
            className="pointer-events-none absolute -right-20 -top-24 h-56 w-56 rounded-full bg-primary/10 blur-3xl"
          />
          <div className="relative flex items-center gap-4">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-6 w-6" />
            </span>
            <div>
              <p className="font-display text-lg font-semibold">
                {formatPeriod(latest.period_start, latest.period_end)}
              </p>
              <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                Visibility score <ScoreBadge score={latest.overall_score} />
              </p>
            </div>
          </div>
          <a
            href={latest.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="relative inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Download className="h-4 w-4" />
            Download PDF
          </a>
        </div>
      </section>

      {/* Earlier reports */}
      {older.length > 0 && (
        <section className="reveal space-y-3" style={{ animationDelay: "60ms" }}>
          <SectionHeading>Earlier Reports</SectionHeading>
          {older.map((r) => (
            <div
              key={r.id}
              className="card-lift flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <FileText className="h-5 w-5" />
                </span>
                <div>
                  <p className="text-sm font-medium">
                    {formatPeriod(r.period_start, r.period_end)}
                  </p>
                  <p className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                    Visibility score <ScoreBadge score={r.overall_score} className="text-[10px]" />
                  </p>
                </div>
              </div>
              <a
                href={r.download_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex shrink-0 items-center gap-1.5 rounded-md border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:bg-secondary"
              >
                <Download className="h-4 w-4" />
                Download PDF
              </a>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
