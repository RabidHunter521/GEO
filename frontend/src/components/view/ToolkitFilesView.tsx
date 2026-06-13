"use client"

// frontend/src/components/view/ToolkitFilesView.tsx
// Read-only client-facing view of the AI Readiness Toolkit. Shows each file
// with a live-verification badge, plain-English implementation instructions,
// and copy/download. No generate/verify actions — those are admin-only.
import { useState } from "react"
import { Copy, Download, Check, CheckCircle2, Circle } from "lucide-react"
import type { ClientViewToolkit } from "@/types"

const FILE_META = {
  llms_txt: {
    label: "llms.txt",
    filename: "llms.txt",
    instruction:
      "This file helps AI search engines understand your site. It lives at yourdomain.com/llms.txt — your SeenBy team uploads it for you, then verifies it's live.",
  },
  schema_json: {
    label: "schema.json",
    filename: "schema.json",
    instruction:
      "Structured data that tells AI systems exactly what your business does, where you are, and what you offer — so you're described accurately.",
  },
  robots_txt: {
    label: "robots.txt",
    filename: "robots.txt",
    instruction:
      "Permissions that explicitly welcome the AI crawlers (GPTBot, PerplexityBot, ClaudeBot, Google-Extended) so they can read and cite your site.",
  },
} as const

type FileKey = keyof typeof FILE_META
const FILE_KEYS: FileKey[] = ["llms_txt", "schema_json", "robots_txt"]

function isVerified(toolkit: ClientViewToolkit, key: FileKey): boolean {
  if (key === "llms_txt") return toolkit.llms_verified
  if (key === "schema_json") return toolkit.schema_verified
  return toolkit.robots_verified
}

export function ToolkitFilesView({ toolkit }: { toolkit: ClientViewToolkit }) {
  const [activeTab, setActiveTab] = useState<FileKey>("llms_txt")
  const [copied, setCopied] = useState(false)

  function handleCopy(value: string) {
    navigator.clipboard.writeText(value)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  function handleDownload(key: FileKey) {
    const blob = new Blob([toolkit[key]], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = FILE_META[key].filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="rounded-xl border bg-card p-5">
      <h2 className="font-display text-lg font-semibold">AI Readiness Files</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        The files we prepared to make your website readable and citable by AI
        search engines. Green means it&apos;s verified live on your site.
      </p>

      {/* Tab bar with per-file verification status */}
      <div className="mt-4 flex gap-0 border-b">
        {FILE_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveTab(key)}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <span className="flex items-center gap-1.5">
              {FILE_META[key].label}
              {isVerified(toolkit, key) ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-score-strong" />
              ) : (
                <Circle className="h-3.5 w-3.5 text-muted-foreground/40" />
              )}
            </span>
          </button>
        ))}
      </div>

      {FILE_KEYS.map((key) =>
        activeTab !== key ? null : (
          <div key={key} className="mt-4 space-y-4">
            {/* Verification badge */}
            <div className="flex items-center gap-2 text-sm">
              {isVerified(toolkit, key) ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-score-strong/30 bg-score-strong-bg px-2.5 py-0.5 text-xs font-medium text-score-strong">
                  <CheckCircle2 className="h-3 w-3" />
                  Verified live on your site
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs text-muted-foreground">
                  <Circle className="h-3 w-3" />
                  Not yet verified
                </span>
              )}
            </div>

            {/* File content */}
            <div className="relative rounded-md border bg-muted/20">
              <div className="absolute right-2 top-2 z-10 flex gap-1">
                <button
                  type="button"
                  onClick={() => handleCopy(toolkit[key])}
                  className="inline-flex h-7 items-center gap-1 rounded-md border bg-background px-2 text-xs font-medium transition-colors hover:bg-secondary"
                >
                  {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                  {copied ? "Copied" : "Copy"}
                </button>
                <button
                  type="button"
                  onClick={() => handleDownload(key)}
                  className="inline-flex h-7 items-center gap-1 rounded-md border bg-background px-2 text-xs font-medium transition-colors hover:bg-secondary"
                >
                  <Download className="h-3 w-3" />
                  Download
                </button>
              </div>
              <textarea
                readOnly
                value={toolkit[key]}
                rows={12}
                className="w-full resize-none rounded-md bg-transparent px-3 py-3 pt-10 font-mono text-xs focus:outline-none"
              />
            </div>

            {/* Plain-English instruction */}
            <div className="rounded-md border bg-muted/10 px-4 py-3">
              <p className="text-sm font-medium">What this does</p>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                {FILE_META[key].instruction}
              </p>
            </div>
          </div>
        ),
      )}
    </div>
  )
}
