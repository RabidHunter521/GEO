import { getAllTruthFacts, getBusinessLocations } from "@/lib/api"
import { TruthVaultClient } from "./TruthVaultClient"

export default async function TruthVaultPage({
  params, searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<{ location?: string }>
}) {
  const { id } = await params
  const { location } = await searchParams
  const locations = await getBusinessLocations(id)
  // The admin selector only exposes active locations. Treat a stale or
  // hand-crafted location query as Brand-wide instead of silently presenting
  // inactive-location facts under the wrong scope label.
  const selectedLocationId = location && locations.some((item) => item.id === location) ? location : null
  const facts = await getAllTruthFacts(id, {
    location_id: selectedLocationId ?? undefined,
    mode: "history",
  })

  return <TruthVaultClient
    key={selectedLocationId ?? "brand"}
    clientId={id}
    locations={locations}
    facts={facts}
    selectedLocationId={selectedLocationId}
  />
}
