"use server"

import { revalidatePath } from "next/cache"
import { generateContentRoadmap as apiGenerate, getContentRoadmap } from "@/lib/api"
import type { ContentRoadmap } from "@/types"

export async function generateRoadmapAction(clientId: string): Promise<ContentRoadmap> {
  const roadmap = await apiGenerate(clientId)
  revalidatePath(`/clients/${clientId}/content-roadmap`)
  return roadmap
}

export async function refreshRoadmapAction(clientId: string): Promise<ContentRoadmap | null> {
  try {
    return await getContentRoadmap(clientId)
  } catch {
    return null
  }
}
