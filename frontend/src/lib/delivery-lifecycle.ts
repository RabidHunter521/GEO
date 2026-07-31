import type { OutcomeActionStatus } from "@/types"

export const OUTCOME_ACTION_TRANSITIONS: Record<OutcomeActionStatus, OutcomeActionStatus[]> = {
  detected: ["recommended", "dismissed"],
  recommended: ["approved_internal", "dismissed", "superseded"],
  approved_internal: ["in_progress", "dismissed"],
  in_progress: ["waiting_client", "ready_to_publish", "dismissed"],
  waiting_client: ["in_progress", "ready_to_publish", "dismissed"],
  ready_to_publish: ["published", "in_progress"],
  published: ["waiting_verification"],
  waiting_verification: ["verified", "no_change"],
  verified: [],
  no_change: ["waiting_verification", "superseded"],
  superseded: [],
  dismissed: [],
}

export const OUTCOME_ACTION_STATUS_LABELS: Record<OutcomeActionStatus, string> = {
  detected: "Detected",
  recommended: "Recommended",
  approved_internal: "Approved internally",
  in_progress: "In progress",
  waiting_client: "Waiting for client",
  ready_to_publish: "Ready to publish",
  published: "Published",
  waiting_verification: "Waiting for verification",
  verified: "Verified",
  no_change: "No change",
  superseded: "Superseded",
  dismissed: "Dismissed",
}

export const TERMINAL_OUTCOME_ACTION_STATUSES: OutcomeActionStatus[] = [
  "verified",
  "no_change",
  "superseded",
  "dismissed",
]

export function validNextStatuses(status: OutcomeActionStatus): OutcomeActionStatus[] {
  return OUTCOME_ACTION_TRANSITIONS[status]
}
