import { getSuggestedWorkLog } from "@/lib/api"
import { ReviewQueueClient } from "./ReviewQueueClient"

export default async function ReviewQueuePage() {
  const suggestions = await getSuggestedWorkLog()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Review Queue</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Work we logged automatically, waiting for your review. Nothing here is
          visible to a client until you publish it.
        </p>
      </div>
      <ReviewQueueClient initialSuggestions={suggestions} />
    </div>
  )
}
