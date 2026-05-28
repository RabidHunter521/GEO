// frontend/src/app/clients/[id]/settings/page.tsx
import { getClient, getCompetitors } from "@/lib/api"
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

  return (
    <div className="max-w-2xl">
      <SettingsForm client={client} competitors={competitors} />
    </div>
  )
}
