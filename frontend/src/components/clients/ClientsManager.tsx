// frontend/src/components/clients/ClientsManager.tsx
// Owns the all-clients grid plus the portfolio dashboard, filter bar, and the
// card selection modes: "remove" archives the picked clients, "scan" bulk
// triggers a scan for each, both without leaving the page.
"use client"

import { useMemo, useState } from "react"
import { Loader2, RefreshCw, Trash2, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { ClientCard } from "@/components/clients/ClientCard"
import { ClientFilterBar } from "@/components/clients/ClientFilterBar"
import { AddClientButton } from "@/components/clients/AddClientButton"
import { NeedsAttentionQueue } from "@/components/clients/NeedsAttentionQueue"
import { PortfolioSummary } from "@/components/clients/PortfolioSummary"
import { archiveClientsAction, bulkScanAction } from "@/app/clients/actions"
import { applyFilters, DEFAULT_FILTERS, type ClientFilters } from "@/lib/client-list-utils"
import type { ClientListItem } from "@/types"

interface Props {
  clients: ClientListItem[]
}

type SelectionMode = "none" | "remove" | "scan"

export function ClientsManager({ clients }: Props) {
  const [selectionMode, setSelectionMode] = useState<SelectionMode>("none")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [filters, setFilters] = useState<ClientFilters>({ ...DEFAULT_FILTERS })
  // Stable per mount — keeps attention/recency math consistent across renders
  const [now] = useState(() => new Date())

  const visible = useMemo(
    () => applyFilters(clients, filters, now),
    [clients, filters, now],
  )

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function cancel() {
    setSelectionMode("none")
    setSelected(new Set())
  }

  async function confirmRemove() {
    if (selected.size === 0) return
    if (
      !window.confirm(
        `Remove ${selected.size} client${selected.size !== 1 ? "s" : ""}? They will be removed from your dashboard.`,
      )
    ) {
      return
    }
    setBusy(true)
    await archiveClientsAction(Array.from(selected))
    setBusy(false)
    cancel()
  }

  async function confirmScan() {
    if (selected.size === 0) return
    if (
      !window.confirm(
        `Run a scan for ${selected.size} client${selected.size !== 1 ? "s" : ""}? Each scan runs on the client's enabled platforms.`,
      )
    ) {
      return
    }
    setBusy(true)
    const { triggered, skipped } = await bulkScanAction(Array.from(selected))
    setBusy(false)
    cancel()
    if (triggered > 0) {
      toast.success(
        `Triggered ${triggered} scan${triggered !== 1 ? "s" : ""}` +
          (skipped > 0 ? ` — ${skipped} skipped (scan already running)` : ""),
      )
    } else if (skipped > 0) {
      toast.warning(`No scans triggered — ${skipped} skipped (scan already running)`)
    }
  }

  const inSelection = selectionMode !== "none"

  return (
    <div>
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">Clients</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {clients.length} client{clients.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <AddClientButton />
          {inSelection ? (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={cancel} disabled={busy}>
                <X className="h-4 w-4 mr-1" />
                Cancel
              </Button>
              {selectionMode === "remove" ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="border-destructive/40 text-destructive hover:bg-destructive/5 hover:text-destructive"
                  disabled={selected.size === 0 || busy}
                  onClick={confirmRemove}
                >
                  {busy ? (
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4 mr-1" />
                  )}
                  Remove{selected.size > 0 ? ` (${selected.size})` : ""}
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  className="border-primary/40 text-primary hover:bg-primary/5 hover:text-primary"
                  disabled={selected.size === 0 || busy}
                  onClick={confirmScan}
                >
                  {busy ? (
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4 mr-1" />
                  )}
                  Scan{selected.size > 0 ? ` (${selected.size})` : ""}
                </Button>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setSelectionMode("scan")}>
                <RefreshCw className="h-4 w-4 mr-1" />
                Scan clients
              </Button>
              <Button variant="outline" size="sm" onClick={() => setSelectionMode("remove")}>
                <Trash2 className="h-4 w-4 mr-1" />
                Remove client
              </Button>
            </div>
          )}
        </div>
      </div>

      {clients.length === 0 ? (
        <div className="rounded-xl border border-dashed bg-card/50 py-16 text-center">
          <p className="font-display text-lg font-semibold">No clients yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Add your first client to get started.
          </p>
          <div className="mt-4 flex justify-center">
            <AddClientButton />
          </div>
        </div>
      ) : (
        <>
          <PortfolioSummary clients={clients} now={now} />
          <NeedsAttentionQueue clients={clients} now={now} />
          <ClientFilterBar
            clients={clients}
            filters={filters}
            onChange={setFilters}
            visibleCount={visible.length}
          />
          {visible.length === 0 ? (
            <div className="rounded-xl border border-dashed bg-card/50 py-16 text-center">
              <p className="font-display text-lg font-semibold">No clients match these filters</p>
              <div className="mt-4 flex justify-center">
                <Button variant="outline" size="sm" onClick={() => setFilters({ ...DEFAULT_FILTERS })}>
                  <X className="h-4 w-4 mr-1" />
                  Clear filters
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {visible.map((client) => (
                <ClientCard
                  key={client.id}
                  client={client}
                  selectMode={inSelection}
                  selected={selected.has(client.id)}
                  onToggle={() => toggle(client.id)}
                  selectionVariant={selectionMode === "scan" ? "primary" : "destructive"}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
