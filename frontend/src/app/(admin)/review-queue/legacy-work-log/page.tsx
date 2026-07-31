import { getSuggestedWorkLog } from "@/lib/api"
import { ReviewQueueClient } from "../ReviewQueueClient"

export default async function LegacyWorkLogReviewQueuePage() {
  const suggestions = await getSuggestedWorkLog()
  return (
    <div className="space-y-6">
      <div><h1 className="font-display text-2xl font-semibold tracking-tight">Legacy work-log suggestions</h1></div>
      <ReviewQueueClient initialSuggestions={suggestions} />
    </div>
  )
}
