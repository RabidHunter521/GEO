import { Activity, CheckCircle, XCircle, Wrench, ShieldCheck, UserPlus, Mail, FileText } from "lucide-react"
import { getActivityLog } from "@/lib/api"
import type { ActivityLogEntry } from "@/types"

interface Props {
  params: Promise<{ id: string }>
}

const EVENT_LABELS: Record<string, string> = {
  scan_completed: "Scan completed",
  scan_failed: "Scan failed",
  toolkit_generated: "Toolkit generated",
  toolkit_verified: "Toolkit files verified",
  client_created: "Client onboarded",
  digest_sent: "Weekly digest sent",
  report_generated: "Monthly report generated",
  report_sent: "Monthly report sent",
}

function EventIcon({ type }: { type: string }) {
  const cls = "h-4 w-4 shrink-0 mt-0.5"
  switch (type) {
    case "scan_completed":
      return <CheckCircle className={`${cls} text-green-500`} />
    case "scan_failed":
      return <XCircle className={`${cls} text-red-500`} />
    case "toolkit_generated":
      return <Wrench className={`${cls} text-blue-500`} />
    case "toolkit_verified":
      return <ShieldCheck className={`${cls} text-purple-500`} />
    case "client_created":
      return <UserPlus className={`${cls} text-muted-foreground`} />
    case "digest_sent":
      return <Mail className={`${cls} text-indigo-500`} />
    case "report_generated":
      return <FileText className={`${cls} text-sky-500`} />
    case "report_sent":
      return <FileText className={`${cls} text-green-500`} />
    default:
      return <Activity className={`${cls} text-muted-foreground`} />
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-MY", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export default async function ActivityPage({ params }: Props) {
  const { id } = await params

  let entries: ActivityLogEntry[] = []
  try {
    entries = await getActivityLog(id)
  } catch {
    // backend down — fall through to empty state
  }

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
        <p className="font-medium">No activity yet</p>
        <p className="text-sm mt-1">
          Activity is recorded when you run scans, generate toolkit files, or verify your implementation.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-0.5">
      <p className="text-sm text-muted-foreground px-4 mb-3">
        Showing the last {entries.length} event{entries.length !== 1 ? "s" : ""}, newest first.
      </p>
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="flex items-start gap-3 rounded-lg px-4 py-3 hover:bg-muted/30 transition-colors"
        >
          <EventIcon type={entry.event_type} />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium leading-none">
              {EVENT_LABELS[entry.event_type] ?? entry.event_type}
            </p>
            <p className="text-sm text-muted-foreground mt-1">{entry.note}</p>
          </div>
          <p className="text-xs text-muted-foreground shrink-0 mt-0.5 tabular-nums">
            {formatDate(entry.created_at)}
          </p>
        </div>
      ))}
    </div>
  )
}
