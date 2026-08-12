// Shared pending-work buckets for /review-queue and /home. Pure and
// serializable — no React. Matchers are independent: one action can match more
// than one bucket (e.g. Overdue + Accuracy review) and appears as a row in each.
import type { OutcomeAction } from "@/types"

/** Minimal client shape the queue needs — decoupled from the full Client type. */
export interface QueueClient {
  id: string
  name: string
}

export interface QueueItem {
  action: OutcomeAction
  client: QueueClient
}

export interface QueueSectionDef {
  title: string
  matches: (action: OutcomeAction, today: string) => boolean
}

export interface GroupedQueueSection {
  title: string
  items: QueueItem[]
}

export interface GroupedQueue {
  /** All buckets in fixed order, including empty ones. */
  sections: GroupedQueueSection[]
  /** Sum of every bucket's item count (rendered rows). */
  totalItems: number
  /** Distinct clients contributing at least one row to any bucket. */
  clientCount: number
}

export const QUEUE_SECTIONS: readonly QueueSectionDef[] = [
  {
    title: "Accuracy review",
    matches: (action) =>
      action.action_type === "accuracy_review" &&
      ["detected", "recommended", "approved_internal"].includes(action.status),
  },
  {
    title: "Client approval",
    matches: (action) => action.status === "waiting_client",
  },
  {
    title: "Publish-ready",
    matches: (action) => action.status === "ready_to_publish",
  },
  {
    title: "Verification-ready",
    matches: (action) => action.status === "waiting_verification",
  },
  {
    title: "Overdue",
    matches: (action, today) =>
      Boolean(
        action.due_date &&
          action.due_date < today &&
          !["verified", "no_change", "superseded", "dismissed"].includes(action.status),
      ),
  },
] as const

export function groupOutcomeActions(
  lists: { client: QueueClient; actions: OutcomeAction[] }[],
  today: string,
): GroupedQueue {
  const sections: GroupedQueueSection[] = QUEUE_SECTIONS.map((section) => ({
    title: section.title,
    items: lists.flatMap(({ client, actions }) =>
      actions
        .filter((action) => section.matches(action, today))
        .map((action) => ({ action, client })),
    ),
  }))

  const totalItems = sections.reduce((sum, section) => sum + section.items.length, 0)
  const clientIds = new Set<string>()
  for (const section of sections) {
    for (const item of section.items) {
      clientIds.add(item.client.id)
    }
  }

  return { sections, totalItems, clientCount: clientIds.size }
}
