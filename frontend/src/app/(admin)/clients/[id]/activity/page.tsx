import Link from "next/link"
import { Activity, CheckCircle, XCircle, Wrench, ShieldCheck, UserPlus, Mail, FileText, Bell, AlertTriangle, ChevronLeft, ChevronRight, Search } from "lucide-react"
import { getActivityLog, getWorkLog } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { parseUtc, presentActivityNote, presentActivityType } from "@/lib/activity-presentation"
import type { ActivityLogEntry } from "@/types"
import { WorkLogCard } from "./WorkLogCard"

interface Props {
  params: Promise<{ id: string }>
  searchParams: Promise<{ page?: string }>
}

const PAGE_SIZE = 100

function EventIcon({ type }: { type: string }) {
  const cls = "h-4 w-4 shrink-0 mt-0.5"
  switch (type) {
    case "scan_completed":
      return <CheckCircle className={`${cls} text-score-strong`} />
    case "scan_failed":
      return <XCircle className={`${cls} text-score-low`} />
    case "toolkit_generated":
      return <Wrench className={`${cls} text-primary`} />
    case "toolkit_verified":
      return <ShieldCheck className={`${cls} text-primary`} />
    case "client_created":
      return <UserPlus className={`${cls} text-muted-foreground`} />
    case "digest_sent":
      return <Mail className={`${cls} text-primary`} />
    case "report_generated":
      return <FileText className={`${cls} text-primary`} />
    case "report_sent":
      return <FileText className={`${cls} text-score-strong`} />
    case "alert_sent":
      return <Bell className={`${cls} text-score-low`} />
    case "hallucination_flagged":
      return <AlertTriangle className={`${cls} text-score-watch`} />
    case "content_analyzed":
      return <Search className={`${cls} text-primary`} />
    default:
      return <Activity className={`${cls} text-muted-foreground`} />
  }
}

// created_at is naive UTC (no zone suffix) — parseUtc appends "Z" so this
// parses as UTC instead of the browser's local zone. See
// src/lib/activity-presentation.ts for why that matters.
function formatDate(iso: string): string {
  return parseUtc(iso).toLocaleString("en-MY", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export default async function ActivityPage({ params, searchParams }: Props) {
  const { id } = await params
  const sp = await searchParams
  const page = Math.max(1, Number(sp.page ?? 1))
  const skip = (page - 1) * PAGE_SIZE

  let entries: ActivityLogEntry[] = []
  let hasMore = false
  try {
    // Fetch one extra to detect if another page exists
    entries = await getActivityLog(id, PAGE_SIZE + 1, skip)
    if (entries.length > PAGE_SIZE) {
      hasMore = true
      entries = entries.slice(0, PAGE_SIZE)
    }
  } catch {
    // backend down — fall through to empty state
  }

  const workLog = await getWorkLog(id).catch(() => [])

  if (entries.length === 0 && page === 1) {
    return (
      <div className="space-y-4">
        <WorkLogCard clientId={id} initialEntries={workLog} />
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <p className="font-medium">The activity timeline will start with the first scan</p>
          <p className="text-sm mt-1">
            Scans, reviewed findings, delivered work, reports, and verification events will appear here.
          </p>
          <Link
            href={`/clients/${id}/scan`}
            className="mt-3 inline-flex items-center text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            Go to Scan &amp; Visibility →
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <WorkLogCard clientId={id} initialEntries={workLog} />
      <p className="text-sm text-muted-foreground">
        Page {page} · showing {entries.length} event{entries.length !== 1 ? "s" : ""}, newest first.
      </p>
      <div className="divide-y rounded-lg border bg-card">
        {entries.map((entry) => {
          const presentation = presentActivityType(entry.event_type)
          return (
            <div
              key={entry.id}
              className="flex items-start gap-3 px-4 py-3 transition-colors hover:bg-muted/30"
            >
              <EventIcon type={entry.event_type} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium leading-none">
                  {presentation.label}
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  {presentActivityNote(entry.note)}
                </p>
              </div>
              <p className="text-xs text-muted-foreground shrink-0 mt-0.5 tabular-nums">
                {formatDate(entry.created_at)}
              </p>
            </div>
          )
        })}
      </div>

      {(page > 1 || hasMore) && (
        <div className="flex items-center justify-between pt-1">
          {page <= 1 ? (
            <Button variant="outline" size="sm" disabled>
              <ChevronLeft className="h-4 w-4 mr-1" />
              Previous
            </Button>
          ) : (
            <Button variant="outline" size="sm" asChild>
              <Link href={`/clients/${id}/activity?page=${page - 1}`}>
                <ChevronLeft className="h-4 w-4 mr-1" />
                Previous
              </Link>
            </Button>
          )}
          <span className="text-sm text-muted-foreground">Page {page}</span>
          {!hasMore ? (
            <Button variant="outline" size="sm" disabled>
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          ) : (
            <Button variant="outline" size="sm" asChild>
              <Link href={`/clients/${id}/activity?page=${page + 1}`}>
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Link>
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
