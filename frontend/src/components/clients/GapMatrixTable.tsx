// frontend/src/components/clients/GapMatrixTable.tsx
// Portfolio-level competitor gap matrix — rows = real clients, columns = WIN_LOSS_CATEGORIES.

import Link from "next/link"
import { AlertTriangle, CheckCircle, Minus } from "lucide-react"
import type { GapMatrixResponse } from "@/types"

const CATEGORY_LABELS: Record<string, string> = {
  recommendation: "Recommendation",
  local: "Local",
}

interface Props {
  matrix: GapMatrixResponse
}

export function GapMatrixTable({ matrix }: Props) {
  if (matrix.rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed bg-card/50 py-16 text-center text-muted-foreground">
        <p className="font-medium">No active clients yet</p>
        <p className="text-sm mt-1">Add clients to see the gap matrix.</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border bg-card overflow-hidden shadow-brand">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/30">
              <th className="px-5 py-3 text-left font-semibold text-foreground w-48">
                Client
              </th>
              {matrix.categories.map((cat) => (
                <th
                  key={cat}
                  className="px-5 py-3 text-left font-semibold text-foreground min-w-[200px]"
                >
                  {CATEGORY_LABELS[cat] ?? cat}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {matrix.rows.map((row) => (
              <tr key={row.client_id} className="hover:bg-muted/10 transition-colors">
                <td className="px-5 py-4 font-medium">
                  <Link
                    href={`/clients/${row.client_id}`}
                    className="hover:text-primary hover:underline underline-offset-4 transition-colors"
                  >
                    {row.client_name}
                  </Link>
                </td>
                {matrix.categories.map((cat) => {
                  const cell = row.cells.find((c) => c.category === cat)

                  // No scan data
                  if (!cell) {
                    return (
                      <td key={cat} className="px-5 py-4 text-muted-foreground/50">
                        <span className="flex items-center gap-1.5">
                          <Minus className="h-3.5 w-3.5" />
                          <span className="text-xs">—</span>
                        </span>
                      </td>
                    )
                  }

                  if (cell.competitors_winning) {
                    // Competitor leading — red
                    return (
                      <td key={cat} className="px-5 py-4">
                        <div className="flex flex-col gap-1">
                          <span className="flex items-center gap-1.5 text-score-watch font-medium text-xs">
                            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                            Your competitors are winning here
                          </span>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span className="tabular-nums">
                              You:{" "}
                              <span className="font-medium">
                                {cell.client_visibility !== null
                                  ? `${cell.client_visibility.toFixed(0)}%`
                                  : "—"}
                              </span>
                            </span>
                            {cell.top_competitor_name && (
                              <>
                                <span className="text-muted-foreground/40">·</span>
                                <span className="tabular-nums">
                                  {cell.top_competitor_name}:{" "}
                                  <span className="font-semibold text-score-watch">
                                    {cell.top_competitor_visibility!.toFixed(0)}%
                                  </span>
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </td>
                    )
                  }

                  if (cell.client_visibility !== null) {
                    // Client leading or tied — green
                    return (
                      <td key={cat} className="px-5 py-4">
                        <div className="flex flex-col gap-1">
                          <span className="flex items-center gap-1.5 text-score-strong font-medium text-xs">
                            <CheckCircle className="h-3.5 w-3.5 shrink-0" />
                            Seen by AI
                          </span>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span className="tabular-nums">
                              You:{" "}
                              <span className="font-semibold text-score-strong">
                                {cell.client_visibility.toFixed(0)}%
                              </span>
                            </span>
                            {cell.top_competitor_name && (
                              <>
                                <span className="text-muted-foreground/40">·</span>
                                <span className="tabular-nums">
                                  {cell.top_competitor_name}:{" "}
                                  <span className="font-medium">
                                    {cell.top_competitor_visibility !== null
                                      ? `${cell.top_competitor_visibility.toFixed(0)}%`
                                      : "—"}
                                  </span>
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </td>
                    )
                  }

                  // client_visibility is null (no own results) and not competitors_winning
                  return (
                    <td key={cat} className="px-5 py-4 text-muted-foreground/50">
                      <span className="flex items-center gap-1.5">
                        <Minus className="h-3.5 w-3.5" />
                        <span className="text-xs">—</span>
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
