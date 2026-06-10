// frontend/src/app/clients/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import { redirect } from "next/navigation"
import {
  createClient as apiCreateClient,
  deleteClient as apiDeleteClient,
  addCompetitor as apiAddCompetitor,
  deleteCompetitor as apiDeleteCompetitor,
} from "@/lib/api"

export async function createClientAction(data: {
  name: string
  website: string
  industry: string
}) {
  const client = await apiCreateClient(data)
  revalidatePath("/clients")
  return client
}

export async function addCompetitorAction(
  clientId: string,
  data: { name: string; website?: string },
) {
  const comp = await apiAddCompetitor(clientId, data)
  revalidatePath(`/clients/${clientId}`)
  return comp
}

export async function deleteCompetitorAction(
  clientId: string,
  competitorId: string,
) {
  await apiDeleteCompetitor(clientId, competitorId)
  revalidatePath(`/clients/${clientId}`)
}

export async function archiveClientAction(id: string) {
  await apiDeleteClient(id)
  revalidatePath("/clients")
  redirect("/clients")
}
