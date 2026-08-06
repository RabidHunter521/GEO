"use client"

import { useState, useTransition } from "react"

import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import type { Client } from "@/types"

import { updateClientAction } from "./actions"

/**
 * Benchmark cohort opt-out.
 *
 * Saves on its own, like the industry pack card, because this is a privacy
 * control rather than an ordinary profile field — the admin should see it
 * commit immediately, not batched inside a large form save.
 *
 * Unlike a pack switch, toggling this is fully reversible and needs no
 * confirmation dialog: opting back in does not retroactively add the client
 * to periods that already published without them, the same way opting out
 * does not retroactively remove them from periods that already published
 * with them. See docs/ops/benchmark-privacy-runbook.md section 4.
 */
export function BenchmarkOptOutCard({ client }: { client: Client }) {
  const [optedOut, setOptedOut] = useState(client.benchmark_opt_out)
  const [saved, setSaved] = useState(client.benchmark_opt_out)
  const [error, setError] = useState<string | null>(null)
  const [pending, startTransition] = useTransition()

  function toggle(next: boolean) {
    setOptedOut(next)
    setError(null)
    startTransition(async () => {
      try {
        await updateClientAction(client.id, { benchmark_opt_out: next })
        setSaved(next)
      } catch (cause) {
        // Revert the checkbox — the request failed, so the saved value is
        // still whatever it was before this click.
        setOptedOut(saved)
        setError(cause instanceof Error ? cause.message : "Could not save this setting.")
      }
    })
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="font-display text-lg font-semibold tracking-tight">Benchmarks</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Whether this client counts toward cohort benchmark comparisons.
        </p>
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex items-start gap-2.5">
        <Checkbox
          id="s-benchmark-opt-out"
          checked={optedOut}
          disabled={pending}
          onCheckedChange={(value) => toggle(value === true)}
          className="mt-0.5"
        />
        <div className="space-y-1">
          <Label htmlFor="s-benchmark-opt-out" className="cursor-pointer font-normal">
            Exclude this client from benchmark comparisons
          </Label>
          <p className="text-xs text-muted-foreground">
            Removes this client from cohort aggregates in both directions: they stop
            contributing to peer numbers and stop receiving a comparison of their own.
            Takes effect for periods computed after you save — it does not change anything
            already published.
          </p>
        </div>
      </div>
    </section>
  )
}
