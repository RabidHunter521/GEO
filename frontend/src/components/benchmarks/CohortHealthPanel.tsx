import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cohortHealth } from "@/lib/benchmark-display"
import type { BenchmarkComparison } from "@/types"

/**
 * Operator-facing summary of how much of a client's benchmark picture is
 * publishable.
 *
 * A high suppression rate is deliberately presented as a data-coverage fact,
 * not a problem to fix. Early in a market almost everything suppresses, and an
 * operator who reads that as a defect will be tempted to lower thresholds —
 * which is exactly the change the database now refuses.
 */
export function CohortHealthPanel({
  comparisons,
}: {
  comparisons: BenchmarkComparison[]
}) {
  const health = cohortHealth(comparisons)

  if (health.isEmpty) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cohort coverage</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          No benchmark metrics have been generated for this period yet.
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Cohort coverage</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Published</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{health.published}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Withheld</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{health.suppressed}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              Withheld rate
            </dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">
              {health.suppressionRate}%
            </dd>
          </div>
        </dl>
        {health.allSuppressed && (
          <p className="mt-4 rounded-md bg-muted p-3 text-sm text-muted-foreground">
            Everything is withheld for this period. That is expected while a market is small:
            a cohort needs at least 10 comparable organisations before any range can be
            published, and the minimum can only ever be raised.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
