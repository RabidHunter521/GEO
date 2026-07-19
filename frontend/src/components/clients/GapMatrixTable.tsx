// frontend/src/components/clients/GapMatrixTable.tsx
// Portfolio-level competitor gap matrix — rows = real clients, columns = WIN_LOSS_CATEGORIES.

import Link from "next/link"
import { AlertTriangle, CheckCircle, Minus, XCircle } from "lucide-react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"
import type { GapCell, GapMatrixResponse } from "@/types"

const CATEGORY_LABELS: Record<string, string> = {
  recommendation: "Recommendation",
  local: "Local",
}

// Presentational-only heuristic for how loudly a losing cell reads — NOT a
// SCORE_BANDS threshold. Every losing cell used to render identical orange
// "competitors winning" text regardless of whether the client trailed by 2
// points or 62, which buried the cells that actually need attention.
const SEVERE_GAP_PTS = 30

function GapBars({ you, competitor, severe }: { you: number; competitor: number; severe: boolean }) {
  return (
    <div className="mt-1.5 space-y-1">
      <div className="flex items-center gap-1.5">
        <span className="w-8 shrink-0 text-[10px] text-muted-foreground">You</span>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary"
            style={{ width: `${Math.max(you, 2)}%` }}
          />
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="w-8 shrink-0 text-[10px] text-muted-foreground">Rival</span>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
          <div
            className={cn("h-full rounded-full", severe ? "bg-score-low" : "bg-score-watch")}
            style={{ width: `${Math.max(competitor, 2)}%` }}
          />
        </div>
      </div>
    </div>
  )
}

function pct(value: number | null): string {
  return value !== null ? `${value.toFixed(0)}%` : "—"
}

function CompetitorTail({ cell }: { cell: GapCell }) {
  if (!cell.top_competitor_name) return null
  return (
    <>
      <span className="text-muted-foreground/40">·</span>
      <span className="tabular-nums">
        {cell.top_competitor_name}:{" "}
        <span className="font-medium">{pct(cell.top_competitor_visibility)}</span>
      </span>
    </>
  )
}

function DashCell() {
  return (
    <span className="flex items-center gap-1.5 text-muted-foreground/50">
      <Minus className="h-3.5 w-3.5" />
      <span className="text-xs">—</span>
    </span>
  )
}

function CellContent({ cell }: { cell: GapCell | undefined }) {
  // No scan data for this category at all.
  if (!cell || cell.client_visibility === null) {
    return <DashCell />
  }

  // A competitor out-performs the client here. Visual intensity scales with
  // how far behind the client is — a 2-point gap and a 62-point gap used to
  // render identically loud, which hid the cells that actually need attention.
  if (cell.competitors_winning) {
    const competitorVisibility = cell.top_competitor_visibility ?? 0
    const gap = competitorVisibility - cell.client_visibility
    const severe = gap >= SEVERE_GAP_PTS
    const gapColor = severe ? "text-score-low" : "text-score-watch"
    return (
      <div className="flex flex-col gap-1">
        <span className={cn("flex items-center gap-1.5 font-medium text-xs", gapColor)}>
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          Your competitors are winning here
        </span>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="tabular-nums">
            You: <span className="font-medium">{pct(cell.client_visibility)}</span>
          </span>
          {cell.top_competitor_name && (
            <>
              <span className="text-muted-foreground/40">·</span>
              <span className="tabular-nums">
                {cell.top_competitor_name}:{" "}
                <span className={cn("font-semibold", gapColor)}>
                  {pct(cell.top_competitor_visibility)}
                </span>
              </span>
            </>
          )}
          {gap > 0 && (
            <span
              className={cn(
                "ml-auto shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold tabular-nums",
                severe ? "bg-score-low-bg text-score-low" : "bg-score-watch-bg text-score-watch",
              )}
            >
              −{Math.round(gap)}pts
            </span>
          )}
        </div>
        <GapBars you={cell.client_visibility} competitor={competitorVisibility} severe={severe} />
      </div>
    )
  }

  // Client has data and competitors aren't winning. Distinguish "Seen by AI"
  // (>0% visibility) from "Not seen by AI" (0% — present in the scan but never
  // surfaced). 0% must NOT render the green "Seen by AI" state.
  const seen = cell.client_visibility > 0
  return (
    <div className="flex flex-col gap-1">
      <span
        className={`flex items-center gap-1.5 font-medium text-xs ${
          seen ? "text-score-strong" : "text-score-watch"
        }`}
      >
        {seen ? (
          <CheckCircle className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <XCircle className="h-3.5 w-3.5 shrink-0" />
        )}
        {seen ? "Seen by AI" : "Not seen by AI"}
      </span>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="tabular-nums">
          You:{" "}
          <span className={seen ? "font-semibold text-score-strong" : "font-medium"}>
            {pct(cell.client_visibility)}
          </span>
        </span>
        <CompetitorTail cell={cell} />
      </div>
    </div>
  )
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
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead scope="col" className="text-foreground font-semibold w-48">
              Client
            </TableHead>
            {matrix.categories.map((cat) => (
              <TableHead
                key={cat}
                scope="col"
                className="text-foreground font-semibold min-w-[200px]"
              >
                {CATEGORY_LABELS[cat] ?? cat}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {matrix.rows.map((row) => (
            <TableRow key={row.client_id}>
              <TableCell className="font-medium">
                <Link
                  href={`/clients/${row.client_id}`}
                  className="hover:text-primary hover:underline underline-offset-4 transition-colors"
                >
                  {row.client_name}
                </Link>
              </TableCell>
              {matrix.categories.map((cat) => (
                <TableCell key={cat}>
                  <CellContent cell={row.cells.find((c) => c.category === cat)} />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
