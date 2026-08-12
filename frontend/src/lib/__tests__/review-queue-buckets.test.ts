import { describe, expect, it } from "vitest"
import type { OutcomeAction } from "@/types"
import { QUEUE_SECTIONS, groupOutcomeActions } from "@/lib/review-queue-buckets"

const TODAY = "2026-08-12"

function makeAction(overrides: Partial<OutcomeAction>): OutcomeAction {
  return {
    id: "a1",
    client_id: "c1",
    scan_id: null,
    work_log_entry_id: null,
    content_deliverable_id: null,
    source_kind: "scan",
    source_ref: null,
    title: "Untitled",
    rationale: "",
    action_type: "content",
    priority: "medium",
    priority_score: null,
    priority_reasons: null,
    confidence: "medium",
    status: "detected",
    owner: null,
    due_date: null,
    destination_url: null,
    client_safe_summary: null,
    verification_result: null,
    published_at: null,
    verified_at: null,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  }
}

function titles(): string[] {
  return QUEUE_SECTIONS.map((s) => s.title)
}

describe("groupOutcomeActions", () => {
  it("returns all five buckets in fixed order, including empties", () => {
    const { sections } = groupOutcomeActions([], TODAY)
    expect(sections.map((s) => s.title)).toEqual([
      "Accuracy review",
      "Client approval",
      "Publish-ready",
      "Verification-ready",
      "Overdue",
    ])
    expect(titles()).toEqual(sections.map((s) => s.title))
  })

  it("is empty for no actions", () => {
    const grouped = groupOutcomeActions(
      [{ client: { id: "c1", name: "Acme" }, actions: [] }],
      TODAY,
    )
    expect(grouped.totalItems).toBe(0)
    expect(grouped.clientCount).toBe(0)
    expect(grouped.sections.every((s) => s.items.length === 0)).toBe(true)
  })

  it("routes each status to its bucket", () => {
    const grouped = groupOutcomeActions(
      [
        {
          client: { id: "c1", name: "Acme" },
          actions: [
            makeAction({ id: "acc", action_type: "accuracy_review", status: "detected" }),
            makeAction({ id: "cli", status: "waiting_client" }),
            makeAction({ id: "pub", status: "ready_to_publish" }),
            makeAction({ id: "ver", status: "waiting_verification" }),
          ],
        },
      ],
      TODAY,
    )
    const by = Object.fromEntries(grouped.sections.map((s) => [s.title, s.items.map((i) => i.action.id)]))
    expect(by["Accuracy review"]).toEqual(["acc"])
    expect(by["Client approval"]).toEqual(["cli"])
    expect(by["Publish-ready"]).toEqual(["pub"])
    expect(by["Verification-ready"]).toEqual(["ver"])
  })

  it("counts an action that matches two buckets once per bucket", () => {
    // accuracy_review + detected + past due_date → Accuracy review AND Overdue.
    const grouped = groupOutcomeActions(
      [
        {
          client: { id: "c1", name: "Acme" },
          actions: [
            makeAction({
              id: "dbl",
              action_type: "accuracy_review",
              status: "detected",
              due_date: "2026-08-01",
            }),
          ],
        },
      ],
      TODAY,
    )
    const accuracy = grouped.sections.find((s) => s.title === "Accuracy review")!
    const overdue = grouped.sections.find((s) => s.title === "Overdue")!
    expect(accuracy.items.map((i) => i.action.id)).toEqual(["dbl"])
    expect(overdue.items.map((i) => i.action.id)).toEqual(["dbl"])
    expect(grouped.totalItems).toBe(2) // two rendered rows
    expect(grouped.clientCount).toBe(1) // one distinct client
  })

  it("excludes terminal-status actions from Overdue", () => {
    const grouped = groupOutcomeActions(
      [
        {
          client: { id: "c1", name: "Acme" },
          actions: [makeAction({ id: "done", status: "verified", due_date: "2026-08-01" })],
        },
      ],
      TODAY,
    )
    expect(grouped.sections.find((s) => s.title === "Overdue")!.items).toHaveLength(0)
    expect(grouped.totalItems).toBe(0)
  })

  it("counts distinct clients, not rows", () => {
    const grouped = groupOutcomeActions(
      [
        {
          client: { id: "c1", name: "Acme" },
          actions: [
            makeAction({ id: "x", status: "waiting_client" }),
            makeAction({ id: "y", status: "ready_to_publish" }),
          ],
        },
      ],
      TODAY,
    )
    expect(grouped.totalItems).toBe(2)
    expect(grouped.clientCount).toBe(1)
  })
})
