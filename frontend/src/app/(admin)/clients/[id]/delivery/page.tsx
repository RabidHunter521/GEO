import { getOutcomeActions } from "@/lib/api"
import { DeliveryClient } from "./DeliveryClient"

export default async function DeliveryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const response = await getOutcomeActions(id, { page_size: 100 })
  return <DeliveryClient clientId={id} initialActions={response.actions} />
}
