import { getContentRoadmap } from "@/lib/api"
import { ContentRoadmapClient } from "./ContentRoadmapClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ContentRoadmapPage({ params }: Props) {
  const { id } = await params
  let roadmap = null
  try {
    roadmap = await getContentRoadmap(id)
  } catch {
    // Backend down or client not found — show empty state
  }
  return <ContentRoadmapClient clientId={id} initialRoadmap={roadmap} />
}
