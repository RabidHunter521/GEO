import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  cellState,
  formatMetricValue,
  hasVersionMismatch,
  isStale,
  opportunityMetrics,
  percentileBandLabel,
  percentileBandSymbol,
  rangeLabel,
  suppressionText,
} from "@/lib/benchmark-display"
import type { BenchmarkComparison } from "@/types"

/**
 * Operator view of one client's position against its cohort.
 *
 * Presentation rules that are not cosmetic:
 *
 * - A withheld cell shows why it is withheld and no numbers at all. Rendering
 *   a dash where a median would go invites the reader to assume zero.
 * - Band chips carry a glyph as well as a colour, so the status survives
 *   colour-blindness and greyscale printing.
 * - The table scrolls inside its own container so the page body never scrolls
 *   horizontally at 360px.
 */
export function PortfolioBenchmarkGrid({
  comparisons,
}: {
  comparisons: BenchmarkComparison[]
}) {
  if (comparisons.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cohort comparison</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          No benchmark data for this period yet.
        </CardContent>
      </Card>
    )
  }

  const period = comparisons[0]
  const stale = isStale(period.period_end)
  const mismatched = hasVersionMismatch(comparisons)
  const opportunities = opportunityMetrics(comparisons)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Cohort comparison
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            {period.period_start} to {period.period_end}
          </span>
        </CardTitle>
        {stale && (
          <p className="text-sm text-amber-700 dark:text-amber-400">
            This is a past period. A newer benchmark has not been generated yet.
          </p>
        )}
        {mismatched && (
          <p className="text-sm text-amber-700 dark:text-amber-400">
            These metrics were calculated under different formula versions and are not
            directly comparable with one another.
          </p>
        )}
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <caption className="sr-only">
              This client&apos;s value against the range for comparable SeenBy clients
            </caption>
            <thead>
              <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th scope="col" className="py-2 pr-4 font-medium">Measure</th>
                <th scope="col" className="py-2 pr-4 font-medium">This client</th>
                <th scope="col" className="py-2 pr-4 font-medium">Cohort range</th>
                <th scope="col" className="py-2 pr-4 font-medium">Position</th>
                <th scope="col" className="py-2 font-medium">Cohort size</th>
              </tr>
            </thead>
            <tbody>
              {comparisons.map((item) => {
                const state = cellState(item)
                if (state !== "published") {
                  return (
                    <tr key={item.metric_key} className="border-b last:border-0">
                      <th scope="row" className="py-3 pr-4 text-left font-medium">
                        {item.metric_label}
                      </th>
                      <td className="py-3 text-muted-foreground" colSpan={4}>
                        {suppressionText(item)}
                      </td>
                    </tr>
                  )
                }
                const band = percentileBandLabel(item.percentile_band)
                return (
                  <tr key={item.metric_key} className="border-b last:border-0">
                    <th scope="row" className="py-3 pr-4 text-left font-medium">
                      {item.metric_label}
                    </th>
                    <td className="py-3 pr-4 tabular-nums">
                      {formatMetricValue(item.client_value, item.metric_key)}
                    </td>
                    <td className="py-3 pr-4 tabular-nums text-muted-foreground">
                      {rangeLabel(item)}
                    </td>
                    <td className="py-3 pr-4">
                      {band && (
                        <Badge
                          variant={
                            item.percentile_band === "bottom_quartile" ? "destructive" : "secondary"
                          }
                        >
                          <span aria-hidden="true" className="mr-1">
                            {percentileBandSymbol(item.percentile_band)}
                          </span>
                          {band}
                        </Badge>
                      )}
                    </td>
                    <td className="py-3 text-muted-foreground">{item.member_count_band}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {opportunities.length > 0 && (
          <div className="mt-6 rounded-md border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30">
            <h3 className="text-sm font-semibold">Where this client trails its cohort</h3>
            <ul className="mt-2 list-inside list-disc text-sm text-muted-foreground">
              {opportunities.map((item) => (
                <li key={item.metric_key}>
                  {item.metric_label} — bottom quarter of {item.member_count_band} comparable
                  businesses
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="mt-4 text-xs text-muted-foreground">{period.caveat}</p>
      </CardContent>
    </Card>
  )
}
