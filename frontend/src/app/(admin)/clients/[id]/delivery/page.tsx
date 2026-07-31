import { getAllOutcomeActions } from "@/lib/api"
import { DeliveryClient } from "./DeliveryClient"

export default async function DeliveryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const actions = await getAllOutcomeActions(id)
  return <DeliveryClient clientId={id} initialActions={actions} />
}
