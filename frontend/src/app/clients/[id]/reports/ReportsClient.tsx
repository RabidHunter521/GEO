"use client"

import { useState, useTransition, useEffect, useRef } from "react"
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { FileText, Download, Send, Loader2 } from "lucide-react"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import type { Report } from "@/types"
import { triggerGenerateReport, triggerSendReport, getReportsAction } from "./actions"

interface Props {
  clientId: string
  initialReports: Report[]
  contactEmail: string | null
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

export function ReportsClient({ clientId, initialReports, contactEmail }: Props) {
  const [reports, setReports] = useState<Report[]>(initialReports)
  const [isPending, startTransition] = useTransition()
  const [sendingId, setSendingId] = useState<string | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)
  const expectedCountRef = useRef(initialReports.length)

  useEffect(() => {
    if (!isGenerating) return
    const interval = setInterval(async () => {
      const updated = await getReportsAction(clientId)
      setReports(updated)
      if (updated.length > expectedCountRef.current) {
        setIsGenerating(false)
      }
    }, 5000)
    const timeout = setTimeout(() => {
      setIsGenerating(false)
      setGenerateError("Report generation timed out — check the Activity Log and try again.")
    }, 90000)
    return () => {
      clearInterval(interval)
      clearTimeout(timeout)
    }
  }, [isGenerating, clientId])

  function handleGenerate() {
    expectedCountRef.current = reports.length
    setIsGenerating(true)
    setGenerateError(null)
    startTransition(async () => {
      await triggerGenerateReport(clientId)
    })
  }

  function handleSend(reportId: string) {
    setSendingId(reportId)
    setSendError(null)
    startTransition(async () => {
      const sent = await triggerSendReport(clientId, reportId)
      setSendingId(null)
      if (!sent) {
        setSendError("no-email")
        return
      }
      const updated = await getReportsAction(clientId)
      setReports(updated)
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">
            Monthly Reports
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Generated automatically 30 days after signup, then every 30 days.
            Review before sending.
          </p>
        </div>
        <Button
          size="sm"
          onClick={handleGenerate}
          disabled={isPending || isGenerating}
        >
          {isPending || isGenerating ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <FileText className="h-4 w-4 mr-2" />
          )}
          Generate Report
        </Button>
      </div>

      {isGenerating && (
        <div className="rounded-lg border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          Report is being generated — this usually takes 30–60 seconds. This page will update automatically.
        </div>
      )}

      {generateError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {generateError}
        </div>
      )}

      {sendError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          Failed to send —{" "}
          <a
            href={`/clients/${clientId}/settings`}
            className="underline underline-offset-4 hover:opacity-80"
          >
            open Settings →
          </a>{" "}
          to add a contact email.
        </div>
      )}

      {reports.length === 0 && !isGenerating && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <FileText className="h-8 w-8 mx-auto mb-3 opacity-40" />
          <p className="font-medium">No reports yet</p>
          <p className="text-sm mt-1">
            Click &ldquo;Generate Report&rdquo; to create the first monthly report.
          </p>
        </div>
      )}

      {reports.length > 0 && (
        <div className="overflow-hidden rounded-lg border bg-card">
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
                    <Badge variant="outline" className="border-score-strong/30 bg-score-strong-bg text-score-strong">
                      Sent {formatDate(report.sent_at)}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="border-score-watch/30 bg-score-watch-bg text-score-watch">
                      Ready for review
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
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={sendingId === report.id || isPending}
                          >
                            {sendingId === report.id ? (
                              <Loader2 className="h-4 w-4 animate-spin mr-1" />
                            ) : (
                              <Send className="h-4 w-4 mr-1" />
                            )}
                            Send to Client
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Send GEO report?</AlertDialogTitle>
                            <AlertDialogDescription>
                              {contactEmail
                                ? <>This will email the report to <strong>{contactEmail}</strong>.</>
                                : "This will send the report to the client's contact email."}
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => handleSend(report.id)}>
                              Send
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        </div>
      )}
    </div>
  )
}
