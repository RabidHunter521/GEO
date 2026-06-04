"use client"

import { useState, useTransition } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { FileText, Download, Send, Loader2 } from "lucide-react"
import type { Report } from "@/types"
import { triggerGenerateReport, triggerSendReport } from "./actions"

interface Props {
  clientId: string
  initialReports: Report[]
}

function formatPeriod(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-MY", {
    month: "long",
    year: "numeric",
  })
}

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-MY", {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
}

function ScoreBadge({ score }: { score: number }) {
  const s = Math.floor(score)
  const variant =
    s >= 65 ? "default" : s >= 50 ? "secondary" : "destructive"
  return <Badge variant={variant}>{score.toFixed(0)}</Badge>
}

export function ReportsClient({ clientId, initialReports }: Props) {
  const [reports] = useState<Report[]>(initialReports)
  const [isPending, startTransition] = useTransition()
  const [sendingId, setSendingId] = useState<string | null>(null)

  function handleGenerate() {
    startTransition(async () => {
      await triggerGenerateReport(clientId)
    })
  }

  function handleSend(reportId: string) {
    setSendingId(reportId)
    startTransition(async () => {
      await triggerSendReport(clientId, reportId)
      setSendingId(null)
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Monthly Reports</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Generated automatically 30 days after signup, then every 30 days.
            Review before sending.
          </p>
        </div>
        <Button
          size="sm"
          onClick={handleGenerate}
          disabled={isPending}
        >
          {isPending ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <FileText className="h-4 w-4 mr-2" />
          )}
          Generate Report
        </Button>
      </div>

      {reports.length === 0 ? (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <FileText className="h-8 w-8 mx-auto mb-3 opacity-40" />
          <p className="font-medium">No reports yet</p>
          <p className="text-sm mt-1">
            Click &ldquo;Generate Report&rdquo; to create the first monthly report.
          </p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Period</TableHead>
              <TableHead>GEO Score</TableHead>
              <TableHead>Generated</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {reports.map((report) => (
              <TableRow key={report.id}>
                <TableCell className="font-medium">
                  {formatPeriod(report.period_start)}
                </TableCell>
                <TableCell>
                  <ScoreBadge score={report.overall_score} />
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {formatDate(report.generated_at)}
                </TableCell>
                <TableCell>
                  {report.sent_at ? (
                    <Badge variant="outline" className="text-green-600 border-green-200">
                      Sent {formatDate(report.sent_at)}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-amber-600 border-amber-200">
                      Not yet sent
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-2">
                    <Button variant="ghost" size="sm" asChild>
                      <a href={report.r2_url} target="_blank" rel="noopener noreferrer">
                        <Download className="h-4 w-4 mr-1" />
                        Download
                      </a>
                    </Button>
                    {!report.sent_at && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleSend(report.id)}
                        disabled={sendingId === report.id || isPending}
                      >
                        {sendingId === report.id ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        ) : (
                          <Send className="h-4 w-4 mr-1" />
                        )}
                        Send to Client
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
