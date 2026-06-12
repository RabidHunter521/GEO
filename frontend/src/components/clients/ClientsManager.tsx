// frontend/src/components/clients/ClientsManager.tsx
// Owns the all-clients grid plus its "remove client" selection mode: toggling
// it overlays a checkbox on each card so the admin can pick clients to
// archive without leaving the page.
"use client"

import { useState } from "react"
import { Trash2, X, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ClientCard } from "@/components/clients/ClientCard"
import { AddClientButton } from "@/components/clients/AddClientButton"
import { archiveClientsAction } from "@/app/clients/actions"
import type { ClientListItem } from "@/types"

interface Props {
  clients: ClientListItem[]
}

export function ClientsManager({ clients }: Props) {
  const [removeMode, setRemoveMode] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [removing, setRemoving] = useState(false)

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function cancel() {
    setRemoveMode(false)
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
    setRemoving(true)
    await archiveClientsAction(Array.from(selected))
    setRemoving(false)
    cancel()
  }

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
          {removeMode ? (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={cancel} disabled={removing}>
                <X className="h-4 w-4 mr-1" />
                Cancel
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="border-destructive/40 text-destructive hover:bg-destructive/5 hover:text-destructive"
                disabled={selected.size === 0 || removing}
                onClick={confirmRemove}
              >
                {removing ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-1" />
                )}
                Remove{selected.size > 0 ? ` (${selected.size})` : ""}
              </Button>
            </div>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setRemoveMode(true)}>
              <Trash2 className="h-4 w-4 mr-1" />
              Remove client
            </Button>
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((client) => (
            <ClientCard
              key={client.id}
              client={client}
              selectMode={removeMode}
              selected={selected.has(client.id)}
              onToggle={() => toggle(client.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
