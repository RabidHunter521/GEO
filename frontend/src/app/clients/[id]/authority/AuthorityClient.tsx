"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import type {
  AuthorityAsset, AuthorityCatalogItem, AuthorityStatus, AuthorityView,
} from "@/types"
import { CatalogPicker } from "./CatalogPicker"
import {
  addAssetsAction, patchAssetAction, verifyAssetAction, addReviewSnapshotAction,
} from "./actions"

const STATUSES: AuthorityStatus[] = ["missing", "in_progress", "live", "verified"]
const STATUS_LABEL: Record<AuthorityStatus, string> = {
  missing: "Missing", in_progress: "In progress", live: "Live", verified: "Verified",
}

export function AuthorityClient({
  clientId, initialView, catalog,
}: {
  clientId: string
  initialView: AuthorityView
  catalog: AuthorityCatalogItem[]
}) {
  const [view, setView] = useState(initialView)
  const [showPicker, setShowPicker] = useState(initialView.assets.length === 0)
  const [pending, setPending] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  async function reloadAfter<T>(fn: () => Promise<T>): Promise<T> {
    setPending(true)
    try {
      return await fn()
    } finally {
      setPending(false)
    }
  }

  function replaceAsset(updated: AuthorityAsset) {
    setView((v) => ({ ...v, assets: v.assets.map((a) => (a.id === updated.id ? updated : a)) }))
  }

  async function handleAdd(keys: string[]) {
    await reloadAfter(async () => {
      await addAssetsAction(clientId, keys.map((k) => ({ asset_key: k })))
      // Server action revalidated the route; pull the fresh view so badges/summary update.
      window.location.reload()
    })
  }

  const s = view.summary
  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-1 py-4 text-sm">
          <span><strong>{s.live}</strong> live</span>
          <span><strong>{s.verified}</strong> verified</span>
          <span className="text-muted-foreground">
            Covers {s.covered_top_domains} of your top {s.total_top_domains || 0} AI source domains
          </span>
          <Button size="sm" variant="outline" className="ml-auto"
                  onClick={() => setShowPicker((x) => !x)}>
            {showPicker ? "Hide catalog" : "Add from catalog"}
          </Button>
        </CardContent>
      </Card>

      {note && <p className="text-sm text-muted-foreground">{note}</p>}

      {showPicker && (
        <Card>
          <CardHeader><CardTitle className="text-base">Add authority assets</CardTitle></CardHeader>
          <CardContent>
            <CatalogPicker catalog={catalog} onAdd={handleAdd} pending={pending} />
          </CardContent>
        </Card>
      )}

      {view.suggested_next.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Suggested next</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Sources AI answers drew from where this client has no live listing yet.
            </p>
            {view.suggested_next.map((d) => (
              <div key={d.domain} className="flex items-center gap-2 text-sm">
                <Badge variant="secondary">{d.count}×</Badge>
                <span className="font-medium">{d.domain}</span>
                {d.catalog_key && (
                  <Button size="sm" variant="ghost" className="ml-auto" disabled={pending}
                          onClick={() => handleAdd([d.catalog_key as string])}>
                    Add as target
                  </Button>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {view.assets.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No authority assets yet. Add the ones relevant to this client from the catalog above.
        </p>
      ) : (
        <div className="space-y-3">
          {view.assets.map((asset) => (
            <Card key={asset.id}>
              <CardContent className="space-y-3 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{asset.name}</span>
                  <Badge variant="outline">{asset.asset_type.replace("_", " ")}</Badge>
                  {asset.seen_in_ai_sources > 0 && (
                    <Badge variant="secondary">Seen in AI sources {asset.seen_in_ai_sources}×</Badge>
                  )}
                  {asset.nap_mismatch && (
                    <Badge variant="destructive">Phone differs from file</Badge>
                  )}
                  <div className="ml-auto w-40">
                    <Select
                      value={asset.status}
                      onValueChange={(value) =>
                        reloadAfter(async () =>
                          replaceAsset(await patchAssetAction(clientId, asset.id, { status: value as AuthorityStatus })))
                      }
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {STATUSES.map((st) => (
                          <SelectItem key={st} value={st}>{STATUS_LABEL[st]}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    defaultValue={asset.url ?? ""}
                    placeholder="Profile URL"
                    className="max-w-md"
                    onBlur={(e) =>
                      e.target.value !== (asset.url ?? "") &&
                      reloadAfter(async () =>
                        replaceAsset(await patchAssetAction(clientId, asset.id, { url: e.target.value })))
                    }
                  />
                  <Button size="sm" variant="outline" disabled={pending || !asset.url}
                          onClick={() =>
                            reloadAfter(async () => {
                              const res = await verifyAssetAction(clientId, asset.id)
                              replaceAsset(res.asset)
                              setNote(res.note)
                            })}>
                    Verify
                  </Button>
                  {asset.last_checked_at && (
                    <span className="text-xs text-muted-foreground">
                      Checked {new Date(asset.last_checked_at).toLocaleDateString()}
                    </span>
                  )}
                </div>

                {asset.asset_type === "review_platform" && (
                  <ReviewSnapshotRow clientId={clientId} asset={asset} onUpdated={replaceAsset}
                                     pending={pending} run={reloadAfter} />
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null
  const max = Math.max(...points), min = Math.min(...points)
  const span = max - min || 1
  const d = points
    .map((p, i) => `${(i / (points.length - 1)) * 100},${20 - ((p - min) / span) * 18}`)
    .join(" ")
  return (
    <svg viewBox="0 0 100 20" className="h-5 w-24" preserveAspectRatio="none" aria-hidden>
      <polyline points={d} fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
    </svg>
  )
}

function ReviewSnapshotRow({
  clientId, asset, onUpdated, pending, run,
}: {
  clientId: string
  asset: AuthorityAsset
  onUpdated: (a: AuthorityAsset) => void
  pending: boolean
  run: <T>(fn: () => Promise<T>) => Promise<T>
}) {
  const [rating, setRating] = useState("")
  const [count, setCount] = useState("")
  const snaps = asset.review_snapshots
  const latest = snaps[snaps.length - 1]
  return (
    <div className="flex flex-wrap items-center gap-2 border-t pt-3 text-sm">
      {latest && (
        <span className="text-muted-foreground">
          {latest.rating}★ · {latest.count} reviews
        </span>
      )}
      <Sparkline points={snaps.map((s) => s.count)} />
      <Input value={rating} onChange={(e) => setRating(e.target.value)}
             placeholder="Rating" className="h-8 w-20" inputMode="decimal" />
      <Input value={count} onChange={(e) => setCount(e.target.value)}
             placeholder="Reviews" className="h-8 w-24" inputMode="numeric" />
      <Button size="sm" variant="outline"
              disabled={pending || !rating || !count}
              onClick={() =>
                run(async () => {
                  onUpdated(await addReviewSnapshotAction(clientId, asset.id, Number(rating), Number(count)))
                  setRating(""); setCount("")
                })}>
        Add this month
      </Button>
    </div>
  )
}
