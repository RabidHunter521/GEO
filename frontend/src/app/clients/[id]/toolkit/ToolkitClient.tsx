"use client"

import { useState, useTransition } from "react"
import { Loader2, Copy, Download, CheckCircle, XCircle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
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
import { toast } from "sonner"
import { copyToClipboard } from "@/lib/utils"
import { generateToolkitAction, verifyToolkitAction } from "./actions"
import type { ToolkitFiles, VerificationResult } from "@/types"

interface Props {
  clientId: string
  initialFiles: ToolkitFiles | null
  clientWebsite: string
}

const FILE_META = {
  llms_txt: {
    label: "llms.txt",
    filename: "llms.txt",
    instruction:
      "Upload this file to your website root so it's accessible at yourdomain.com/llms.txt. Most hosting providers let you upload via FTP or file manager. No plugin or configuration needed.",
    expectedUrl: "/llms.txt",
  },
  schema_json: {
    label: "schema.json",
    filename: "schema.json",
    instruction:
      'Upload this file to your website root (yourdomain.com/schema.json), or embed its contents between <script type="application/ld+json"> tags in your site\'s <head>. WordPress users: use the "Schema & Structured Data for WP" plugin and paste the JSON there.',
    expectedUrl: "/schema.json",
  },
  robots_txt: {
    label: "robots.txt",
    filename: "robots.txt",
    instruction:
      "Copy these lines and paste them at the bottom of your existing robots.txt file (yourdomain.com/robots.txt). If you don't have a robots.txt yet, create one and use this as its full content.",
    expectedUrl: "/robots.txt",
  },
} as const

type FileKey = keyof typeof FILE_META
const FILE_KEYS: FileKey[] = ["llms_txt", "schema_json", "robots_txt"]

export function ToolkitClient({ clientId, initialFiles, clientWebsite }: Props) {
  function fullUrl(path: string): string {
    if (!clientWebsite) return path
    const base = clientWebsite.startsWith("http") ? clientWebsite : `https://${clientWebsite}`
    return base.replace(/\/$/, "") + path
  }
  const [files, setFiles] = useState<ToolkitFiles | null>(initialFiles)
  const [activeTab, setActiveTab] = useState<FileKey>("llms_txt")
  const [verification, setVerification] = useState<VerificationResult | null>(null)

  const [isPending, startGenTransition] = useTransition()
  const [isVerifying, startVerifyTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function handleGenerate() {
    startGenTransition(async () => {
      setError(null)
      try {
        const result = await generateToolkitAction(clientId)
        setFiles(result)
        setVerification(null)
      } catch {
        setError("Failed to generate files. Please try again.")
      }
    })
  }

  function handleVerify() {
    startVerifyTransition(async () => {
      setError(null)
      try {
        const result = await verifyToolkitAction(clientId)
        setVerification(result)
        if (files) {
          setFiles({
            ...files,
            llms_verified: result.llms_verified,
            schema_verified: result.schema_verified,
            robots_verified: result.robots_verified,
          })
        }
      } catch {
        setError("Verification failed. Please try again.")
      }
    })
  }

  async function handleCopy(key: FileKey) {
    const ok = await copyToClipboard(files![key])
    toast[ok ? "success" : "error"](
      ok ? "Copied to clipboard" : "Couldn't copy — select the text and copy manually.",
    )
  }

  function handleDownload(key: FileKey) {
    const blob = new Blob([files![key]], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = FILE_META[key].filename
    a.click()
    URL.revokeObjectURL(url)
  }

  function isVerified(key: FileKey): boolean {
    if (!files) return false
    if (key === "llms_txt") return files.llms_verified
    if (key === "schema_json") return files.schema_verified
    return files.robots_verified
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-display text-xl font-semibold tracking-tight">
            AI Readiness Toolkit
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Generate the three files that make your client visible to AI search engines.
            Each verified file unlocks score points.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {files && (
            <Button variant="outline" onClick={handleVerify} disabled={isVerifying}>
              {isVerifying ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Verify live
            </Button>
          )}
          {files ? (
            // Regenerating overwrites the current files and clears their
            // verified-live status — confirm before discarding them.
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button disabled={isPending}>
                  {isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Regenerate
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Regenerate the toolkit files?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This replaces the current llms.txt, schema.json and robots.txt with
                    freshly generated versions and clears their verified-live status. Any
                    edits you made to the current files will be lost.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleGenerate}>Regenerate</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : (
            <Button onClick={handleGenerate} disabled={isPending}>
              {isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Generate files
            </Button>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Empty state */}
      {!files && !isPending && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <p className="font-medium">No files generated yet</p>
          <p className="text-sm mt-1">
            Click &ldquo;Generate files&rdquo; to create your AI readiness toolkit.
          </p>
        </div>
      )}

      {/* Generating state */}
      {isPending && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-3" />
          <p className="text-sm font-medium">Generating files with Claude AI&hellip;</p>
          <p className="text-xs mt-1">This usually takes 10&ndash;20 seconds.</p>
        </div>
      )}

      {/* Files UI */}
      {files && !isPending && (
        <>
          {/* Tab bar */}
          <div className="flex gap-0 border-b">
            {FILE_KEYS.map((key) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                  activeTab === key
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <span className="flex items-center gap-1.5">
                  {FILE_META[key].label}
                  {isVerified(key) ? (
                    <CheckCircle className="h-3.5 w-3.5 text-score-strong" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-muted-foreground/40" />
                  )}
                </span>
              </button>
            ))}
          </div>

          {/* Tab content */}
          {FILE_KEYS.map((key) =>
            activeTab !== key ? null : (
              <div key={key} className="space-y-4">
                {/* File content area */}
                <div className="relative rounded-md border bg-muted/20">
                  <div className="absolute top-2 right-2 flex gap-1 z-10">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs bg-background"
                      onClick={() => handleCopy(key)}
                    >
                      <Copy className="h-3 w-3 mr-1" />
                      Copy
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs bg-background"
                      onClick={() => handleDownload(key)}
                    >
                      <Download className="h-3 w-3 mr-1" />
                      Download
                    </Button>
                  </div>
                  <textarea
                    readOnly
                    value={files[key]}
                    rows={14}
                    className="w-full rounded-md bg-transparent px-3 py-3 pt-10 text-xs font-mono resize-none focus:outline-none"
                  />
                </div>

                {/* Instructions */}
                <div className="rounded-md border bg-muted/10 px-4 py-3 space-y-2">
                  <p className="text-sm font-medium">How to implement</p>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {FILE_META[key].instruction}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Expected URL:{" "}
                    <code className="font-mono bg-muted px-1 py-0.5 rounded text-xs">
                      {fullUrl(FILE_META[key].expectedUrl)}
                    </code>
                  </p>
                </div>

                {/* Verification badge */}
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Live status:</span>
                  {isVerified(key) ? (
                    <Badge className="gap-1 border-score-strong/30 bg-score-strong-bg text-score-strong">
                      <CheckCircle className="h-3 w-3" />
                      Verified live
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground gap-1">
                      <XCircle className="h-3 w-3" />
                      Not yet verified
                    </Badge>
                  )}
                </div>
              </div>
            )
          )}

          {/* Score impact panel — shown after any verification attempt */}
          {verification && (
            <div className="rounded-md border px-4 py-3 space-y-2">
              <p className="text-sm font-semibold">Score impact</p>
              <div className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Technical Foundations (10 pts)</span>
                  {verification.technical_foundations_updated ? (
                    <span className="text-score-strong font-medium">&#10003; Unlocked &mdash; llms.txt + robots.txt live</span>
                  ) : (
                    <span className="text-muted-foreground">Needs llms.txt + robots.txt live at your domain</span>
                  )}
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Structured Data (10 pts)</span>
                  {verification.structured_data_updated ? (
                    <span className="text-score-strong font-medium">&#10003; Unlocked &mdash; schema.json is live</span>
                  ) : (
                    <span className="text-muted-foreground">Needs schema.json live at your domain</span>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
