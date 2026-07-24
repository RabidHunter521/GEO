"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import type { AuthorityCatalogItem } from "@/types"

interface Props {
  catalog: AuthorityCatalogItem[]
  onAdd: (keys: string[]) => Promise<void>
  pending: boolean
}

export function CatalogPicker({ catalog, onAdd, pending }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const selectable = catalog.filter((c) => !c.added)

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  if (selectable.length === 0) {
    return <p className="text-sm text-muted-foreground">Every catalog item has been added.</p>
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        {selectable.map((item) => (
          <label
            key={item.key}
            htmlFor={`cat-${item.key}`}
            className="flex items-start gap-2 rounded-md border p-2.5 text-sm cursor-pointer hover:bg-muted/50"
          >
            <Checkbox
              id={`cat-${item.key}`}
              checked={selected.has(item.key)}
              onCheckedChange={() => toggle(item.key)}
            />
            <span>
              <span className="font-medium">{item.name}</span>
              <span className="block text-xs text-muted-foreground">{item.type.replace("_", " ")}</span>
            </span>
          </label>
        ))}
      </div>
      <Button
        size="sm"
        disabled={selected.size === 0 || pending}
        onClick={async () => {
          await onAdd([...selected])
          setSelected(new Set())
        }}
      >
        Add selected ({selected.size})
      </Button>
    </div>
  )
}
