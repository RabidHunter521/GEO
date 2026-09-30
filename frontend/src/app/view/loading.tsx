// First load of a client view link: the [token] layout awaits the overview
// before it renders, so this covers the whole shell until then.
import { Skeleton } from "@/components/ui/skeleton"
import { ViewPageSkeleton } from "@/components/view/ViewPageSkeleton"

export default function Loading() {
  return (
    <div className="min-h-screen bg-app-wash">
      <div className="border-b bg-card">
        <div className="mx-auto max-w-[1400px] space-y-3 px-4 py-6 sm:px-6">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-7 w-64" />
          <Skeleton className="h-9 w-full max-w-xl" />
        </div>
      </div>
      <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
        <ViewPageSkeleton />
      </div>
    </div>
  )
}
