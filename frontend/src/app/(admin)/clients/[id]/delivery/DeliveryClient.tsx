"use client"

import { useState } from "react"
import { ActionBoard } from "@/components/delivery/ActionBoard"
import { ActionDetailDialog } from "@/components/delivery/ActionDetailDialog"
import type { OutcomeAction, OutcomeActionPatch, OutcomeActionStatus } from "@/types"
import { patchOutcomeActionAction, transitionOutcomeActionAction } from "./actions"

export function DeliveryClient({ clientId, initialActions }: { clientId: string; initialActions: OutcomeAction[] }) {
  const [actions, setActions] = useState(initialActions)
  const [selected, setSelected] = useState<OutcomeAction | null>(null)
  const [showCompleted, setShowCompleted] = useState(false)

  function replaceAction(next: OutcomeAction) {
    setActions((current) => current.map((action) => action.id === next.id ? next : action))
    setSelected(next)
  }

  async function patch(actionId: string, body: OutcomeActionPatch) {
    const next = await patchOutcomeActionAction(clientId, actionId, body)
    replaceAction(next)
    return next
  }

  async function transition(actionId: string, status: OutcomeActionStatus) {
    const next = await transitionOutcomeActionAction(clientId, actionId, status)
    replaceAction(next)
    return next
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-xl font-semibold">Delivery</h2>
        <p className="mt-1 text-sm text-muted-foreground">Outcome actions tracked from recommendation through verification.</p>
      </div>
      <ActionBoard actions={actions} showCompleted={showCompleted} onShowCompletedChange={setShowCompleted} onSelect={setSelected} />
      <ActionDetailDialog action={selected} open={selected !== null} onOpenChange={(open) => !open && setSelected(null)} onPatch={patch} onTransition={transition} />
    </div>
  )
}
