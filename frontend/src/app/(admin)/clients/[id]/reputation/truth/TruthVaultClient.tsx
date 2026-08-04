"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent } from "@/components/ui/card"
import { FactEditor } from "@/components/truth/FactEditor"
import { LocationSelector } from "@/components/truth/LocationSelector"
import { factTypesFor, fieldsForFactType } from "@/lib/industry-packs"
import type {
  BusinessLocation, BusinessLocationInput, TruthFact, TruthFactDraftInput,
} from "@/types"
import {
  approveFactVersionAction, createFactAction, createLocationAction, deactivateLocationAction,
  draftFactVersionAction, updateLocationAction,
} from "./actions"

const GROUPS = [
  { title: "Identity", factType: "business", matches: ["business", "identity", "name"] },
  { title: "Contact", factType: "contact", matches: ["contact", "location"] },
  { title: "Offering", factType: "offering", matches: ["offering", "offer", "service", "product"] },
  { title: "Credentials", factType: "credential", matches: ["credential", "credentials", "certification"] },
  { title: "Policies", factType: "policy", matches: ["policy", "policies", "restriction", "claim"] },
  { title: "Sources", factType: "source", matches: ["source", "sources"] },
] as const

function groupFor(fact: TruthFact) {
  return GROUPS.find((group) => group.matches.includes(fact.fact_type.toLowerCase() as never)) ?? GROUPS[0]
}

/** "practitioner" -> "Practitioner", "local_service" -> "Local service". */
function factTypeLabel(factType: string): string {
  const spaced = factType.replaceAll("_", " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function TruthVaultClient({
  clientId, locations: initialLocations, facts: initialFacts, selectedLocationId,
  packKey = null,
}: {
  clientId: string
  locations: BusinessLocation[]
  facts: TruthFact[]
  selectedLocationId: string | null
  /** The client's industry pack, when one has been reviewed. */
  packKey?: string | null
}) {
  // Pack-driven groups, one FactEditor per fact type the pack declares.
  const packGroups = factTypesFor(packKey).map((factType) => ({
    factType,
    title: factTypeLabel(factType),
    fields: fieldsForFactType(packKey, factType),
  }))
  const packFactTypes = new Set(packGroups.map((group) => group.factType))
  const orphanedFacts = packGroups.length > 0
    ? initialFacts.filter((fact) => !packFactTypes.has(fact.fact_type))
    : []

  const router = useRouter()
  const [locations, setLocations] = useState(initialLocations)
  const [facts, setFacts] = useState(initialFacts)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function mutation<T>(run: () => Promise<T>): Promise<T> {
    setPending(true)
    setError(null)
    try { return await run() }
    catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not save that change."
      setError(message)
      throw cause
    } finally { setPending(false) }
  }

  async function createLocation(input: Required<Pick<BusinessLocationInput, "name">> & BusinessLocationInput) {
    const location = await mutation(() => createLocationAction(clientId, input))
    setLocations((current) => [
      ...current.map((item) => input.is_primary ? { ...item, is_primary: false } : item),
      location,
    ].sort((a, b) => Number(b.is_primary) - Number(a.is_primary) || a.name.localeCompare(b.name)))
  }

  async function updateLocation(locationId: string, input: BusinessLocationInput) {
    const location = await mutation(() => updateLocationAction(clientId, locationId, input))
    setLocations((current) => current.map((item) =>
      item.id === location.id ? location : location.is_primary ? { ...item, is_primary: false } : item,
    ))
  }

  async function deactivateLocation(location: BusinessLocation, replacementId: string | null) {
    const replacement = replacementId
      ? locations.find((item) => item.id === replacementId && item.active && item.id !== location.id)
      : undefined
    if (location.is_primary && !replacement) {
      throw new Error("Select another active location as the new primary before deactivating this location.")
    }
    await mutation(() => deactivateLocationAction(clientId, location.id, replacement?.id ?? null))
    setLocations((current) => current
      .filter((item) => item.id !== location.id)
      .map((item) => ({ ...item, is_primary: replacement ? item.id === replacement.id : item.is_primary })))
    if (selectedLocationId === location.id) router.push(`/clients/${clientId}/reputation/truth`)
  }

  async function createFact(input: Pick<TruthFact, "fact_type" | "fact_key" | "location_id">) {
    const fact = await mutation(() => createFactAction(clientId, input))
    setFacts((current) => [...current, fact])
    return fact
  }

  async function draftVersion(factId: string, input: TruthFactDraftInput) {
    const version = await mutation(() => draftFactVersionAction(clientId, factId, input))
    setFacts((current) => current.map((fact) => fact.id === factId
      ? { ...fact, versions: [version, ...fact.versions] }
      : fact,
    ))
    return version
  }

  async function approveVersion(factId: string, versionId: string, approvedBy: string) {
    const version = await mutation(() => approveFactVersionAction(clientId, factId, versionId, approvedBy))
    setFacts((current) => current.map((fact) => fact.id === factId
      ? { ...fact, versions: fact.versions.map((item) => item.id === versionId ? version : item) }
      : fact,
    ))
    return version
  }

  const selectedLocation = locations.find((location) => location.id === selectedLocationId)
  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-4 py-5">
          <div>
            <h2 className="font-display text-xl font-semibold tracking-tight">Business Truth Vault</h2>
            <p className="mt-1 text-sm text-muted-foreground">Maintain approved, dated business facts. Every edit is a reviewable draft and history remains immutable.</p>
          </div>
          <LocationSelector
            locations={locations}
            selectedLocationId={selectedLocationId}
            pending={pending}
            onCreate={createLocation}
            onUpdate={updateLocation}
            onDeactivate={deactivateLocation}
          />
          <p className="text-sm text-muted-foreground">Editing scope: <span className="font-medium text-foreground">{selectedLocation ? selectedLocation.name : "Brand-wide"}</span></p>
        </CardContent>
      </Card>

      {error && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

      {/* A client with an industry pack gets that pack's fact groups, so the
          form asks for what the pack actually tracks. Without a pack the
          original generic groups are unchanged. */}
      <div className="grid gap-4 xl:grid-cols-2">
        {packGroups.length > 0
          ? packGroups.map((group) => (
              <FactEditor
                key={group.factType}
                title={group.title}
                factType={group.factType}
                facts={facts.filter((fact) => fact.fact_type === group.factType)}
                locationId={selectedLocationId}
                pending={pending}
                packFields={group.fields}
                onCreateFact={createFact}
                onDraftVersion={draftVersion}
                onApproveVersion={approveVersion}
              />
            ))
          : GROUPS.map((group) => (
              <FactEditor
                key={group.title}
                title={group.title}
                factType={group.factType}
                facts={facts.filter((fact) => groupFor(fact).title === group.title)}
                locationId={selectedLocationId}
                pending={pending}
                onCreateFact={createFact}
                onDraftVersion={draftVersion}
                onApproveVersion={approveVersion}
              />
            ))}
      </div>

      {/* Facts recorded under a previous pack are preserved, so surface them
          rather than letting reviewed work silently disappear from the page. */}
      {packGroups.length > 0 && orphanedFacts.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {orphanedFacts.length} fact{orphanedFacts.length === 1 ? "" : "s"} recorded outside
          this pack {orphanedFacts.length === 1 ? "is" : "are"} kept and still used for accuracy
          checks: {[...new Set(orphanedFacts.map((fact) => fact.fact_type))].join(", ")}.
        </p>
      )}
    </div>
  )
}
