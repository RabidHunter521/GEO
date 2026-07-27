import { getContentGaps } from "@/lib/api"
import { ContentGapsClient } from "./ContentGapsClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ContentGapsPage({ params }: Props) {
  const { id } = await params
  let analysis = null
  try {
    analysis = await getContentGaps(id)
  } catch {
    // Backend down or client not found — show empty state
  }
  return <ContentGapsClient clientId={id} initialAnalysis={analysis} />
}
