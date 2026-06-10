export default function ClientOverviewLoading() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Score hero skeleton */}
      <div className="flex flex-col gap-6 rounded-xl border bg-card p-6 shadow-brand sm:flex-row sm:items-center">
        {/* Ring */}
        <div className="flex h-28 w-28 shrink-0 items-center justify-center self-center">
          <div className="h-28 w-28 rounded-full bg-muted" />
        </div>
        <div className="flex-1 space-y-3">
          <div className="h-3 w-28 rounded-full bg-muted" />
          <div className="h-6 w-36 rounded-full bg-muted" />
          <div className="h-3 w-64 rounded-full bg-muted" />
        </div>
      </div>

      {/* Dimension cards skeleton */}
      <div>
        <div className="mb-3 h-3 w-32 rounded-full bg-muted" />
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="rounded-lg border bg-card p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-2">
                  <div className="h-3.5 w-32 rounded-full bg-muted" />
                  <div className="h-3 w-24 rounded-full bg-muted" />
                </div>
                <div className="h-6 w-12 rounded-full bg-muted" />
              </div>
              <div className="h-1.5 w-full rounded-full bg-muted" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
