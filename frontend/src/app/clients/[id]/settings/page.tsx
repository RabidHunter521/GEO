// frontend/src/app/clients/[id]/settings/page.tsx
import { getClient, getCompetitors, getContentGaps } from "@/lib/api"
import { SettingsForm } from "./SettingsForm"

export default async function SettingsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const [client, competitors] = await Promise.all([
    getClient(id),
    getCompetitors(id),
  ])

  // Content Quality assist — latest crawl-derived recommendation (informational; never auto-scores)
  let contentRecommendation: string | null = null
  try {
    const analysis = await getContentGaps(id)
    contentRecommendation = analysis?.content_quality_recommendation ?? null
  } catch {
    // no analysis yet — hint simply won't show
  }

  return (
    <div className="max-w-2xl">
      <SettingsForm
        client={client}
        competitors={competitors}
        contentRecommendation={contentRecommendation}
      />
    </div>
  )
}
