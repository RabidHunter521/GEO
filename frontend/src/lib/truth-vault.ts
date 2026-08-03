import type { BusinessLocation } from "@/types"

/** Locations that may safely become primary before a primary is deactivated. */
export function primaryReplacementCandidates(
  locations: BusinessLocation[],
  primaryLocationId: string,
): BusinessLocation[] {
  return locations.filter((location) => location.active && location.id !== primaryLocationId)
}
