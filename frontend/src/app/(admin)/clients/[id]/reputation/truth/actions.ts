"use server"

import { revalidatePath } from "next/cache"
import {
  approveTruthFactVersion,
  createBusinessLocation,
  createTruthFact,
  deactivateBusinessLocation,
  draftTruthFactVersion,
  patchBusinessLocation,
} from "@/lib/api"
import type {
  BusinessLocation, BusinessLocationInput, TruthFact, TruthFactDraftInput, TruthFactVersion,
} from "@/types"

const path = (clientId: string) => `/clients/${clientId}/reputation/truth`

export async function createLocationAction(
  clientId: string, input: Required<Pick<BusinessLocationInput, "name">> & BusinessLocationInput,
): Promise<BusinessLocation> {
  const location = await createBusinessLocation(clientId, input)
  revalidatePath(path(clientId))
  return location
}

export async function updateLocationAction(
  clientId: string, locationId: string, input: BusinessLocationInput,
): Promise<BusinessLocation> {
  const location = await patchBusinessLocation(clientId, locationId, input)
  revalidatePath(path(clientId))
  return location
}

export async function deactivateLocationAction(clientId: string, locationId: string): Promise<void> {
  await deactivateBusinessLocation(clientId, locationId)
  revalidatePath(path(clientId))
}

export async function createFactAction(
  clientId: string,
  input: Pick<TruthFact, "fact_type" | "fact_key" | "location_id">,
): Promise<TruthFact> {
  const fact = await createTruthFact(clientId, input)
  revalidatePath(path(clientId))
  return fact
}

export async function draftFactVersionAction(
  clientId: string, factId: string, input: TruthFactDraftInput,
): Promise<TruthFactVersion> {
  const version = await draftTruthFactVersion(clientId, factId, input)
  revalidatePath(path(clientId))
  return version
}

export async function approveFactVersionAction(
  clientId: string, factId: string, versionId: string, approvedBy: string,
): Promise<TruthFactVersion> {
  const version = await approveTruthFactVersion(clientId, factId, versionId, approvedBy)
  revalidatePath(path(clientId))
  return version
}
