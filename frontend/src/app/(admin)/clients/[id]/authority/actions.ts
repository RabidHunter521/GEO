"use server"

import { revalidatePath } from "next/cache"
import {
  addAuthorityAssets,
  patchAuthorityAsset,
  verifyAuthorityAsset,
  addAuthorityReviewSnapshot,
} from "@/lib/api"
import type {
  AddAuthorityAssetItem, AuthorityAsset, AuthorityStatus, AuthorityVerifyResponse,
} from "@/types"

const path = (clientId: string) => `/clients/${clientId}/authority`

export async function addAssetsAction(
  clientId: string, items: AddAuthorityAssetItem[],
): Promise<AuthorityAsset[]> {
  const rows = await addAuthorityAssets(clientId, items)
  revalidatePath(path(clientId))
  return rows
}

export async function patchAssetAction(
  clientId: string, assetId: string,
  patch: { status?: AuthorityStatus; url?: string; notes?: string; hidden?: boolean },
): Promise<AuthorityAsset> {
  const row = await patchAuthorityAsset(clientId, assetId, patch)
  revalidatePath(path(clientId))
  return row
}

export async function verifyAssetAction(
  clientId: string, assetId: string,
): Promise<AuthorityVerifyResponse> {
  const res = await verifyAuthorityAsset(clientId, assetId)
  revalidatePath(path(clientId))
  return res
}

export async function addReviewSnapshotAction(
  clientId: string, assetId: string, rating: number, count: number,
): Promise<AuthorityAsset> {
  const row = await addAuthorityReviewSnapshot(clientId, assetId, rating, count)
  revalidatePath(path(clientId))
  return row
}
