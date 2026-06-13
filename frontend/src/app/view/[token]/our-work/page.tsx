// frontend/src/app/view/[token]/our-work/page.tsx
// Read-only "what we've done for you": AI Readiness Toolkit status + an
// activity-log timeline of client-meaningful events. Proof of work.
import {
  Search,
  FileText,
  CheckCircle2,
  Layers,
  Map,
  Send,
  Activity,
} from "lucide-react"
import { getViewToolkit, getViewActivity } from "@/lib/view-api"
import { ToolkitFilesView } from "@/components/view/ToolkitFilesView"

const ACTIVITY_ICON: Record<string, typeof Search> = {
  scan: Search,
  toolkit: FileText,
  verified: CheckCircle2,
  content: Layers,
  roadmap: Map,
  report: Send,
}

export default async function ViewOurWorkPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const [toolkit, activity] = await Promise.all([
    getViewToolkit(token),
    getViewActivity(token),
  ])

  return (
    <div className="space-y-6">
      {toolkit ? (
        <ToolkitFilesView toolkit={toolkit} />
      ) : (
        <div className="rounded-xl border bg-card p-8 text-center">
          <FileText className="mx-auto h-8 w-8 text-muted-foreground/50" />
          <p className="mt-3 font-display text-lg font-semibold">
            Your AI Readiness files are being prepared
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Your SeenBy team is generating the files that make your website
            readable and citable by AI search engines. They&apos;ll appear here.
          </p>
        </div>
      )}

      {/* Activity timeline */}
      <div>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          <Activity className="h-4 w-4" />
          What We&apos;ve Done
        </h2>
        {activity && activity.length > 0 ? (
          <ol className="relative space-y-4 border-l pl-6">
            {activity.map((event, i) => {
              const Icon = ACTIVITY_ICON[event.kind] ?? Activity
              return (
                <li key={`${event.created_at}-${i}`} className="relative">
                  <span className="absolute -left-[31px] flex h-6 w-6 items-center justify-center rounded-full border bg-card text-primary">
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                  <div className="rounded-lg border bg-card p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium">{event.label}</p>
                      <p className="shrink-0 text-xs text-muted-foreground">
                        {new Date(event.created_at).toLocaleDateString("en-MY", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </p>
                    </div>
                    {event.note && (
                      <p className="mt-1 text-sm text-muted-foreground">{event.note}</p>
                    )}
                  </div>
                </li>
              )
            })}
          </ol>
        ) : (
          <div className="rounded-xl border bg-card p-8 text-center">
            <p className="text-sm text-muted-foreground">
              Activity from your SeenBy team will appear here as work gets done.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
