"use client"

// Lead-source attribution setup + results: the tracked WhatsApp link and
// website snippet, the "how did you hear about us?" webhook, a form for
// answers staff collect by phone, and the last 90 days of signals.
// AI-matched signals land on the evidence ladder as "attributed" results.
import { useState, useTransition } from "react"
import { Copy, KeyRound, MessageCircle, Plus } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { copyToClipboard } from "@/lib/utils"
import { timeAgo } from "@/lib/relative-time"
import type {
  AnswerEventType,
  AttributionChannelSummary,
  AttributionOverview,
  AttributionSignal,
} from "@/types"
import {
  logAnswerAction,
  rotateWebhookSecretAction,
  updateAttributionAction,
} from "./attribution-actions"

const EVENT_TYPES: { value: AnswerEventType; label: string }[] = [
  { value: "lead", label: "Enquiry" },
  { value: "booking", label: "Booking" },
  { value: "call", label: "Phone call" },
  { value: "purchase", label: "Purchase" },
  { value: "form_submit", label: "Form submission" },
]

const MATCH_LABELS: Record<NonNullable<AttributionSignal["match_reason"]>, string> = {
  referrer: "arrived from",
  utm: "link tagged",
  self_reported: "said",
}

function examplePayload(): string {
  return JSON.stringify(
    {
      submission_id: "unique-id-from-your-form",
      answer: "ChatGPT",
      event_type: "lead",
      value_minor: 0,
      currency: "MYR",
    },
    null,
    2,
  )
}

async function copy(text: string, what: string) {
  const ok = await copyToClipboard(text)
  toast[ok ? "success" : "error"](ok ? `${what} copied` : `Couldn't copy the ${what.toLowerCase()}`)
}

function ChannelStat({ title, summary }: { title: string; summary: AttributionChannelSummary }) {
  const platforms = Object.entries(summary.by_platform)
  return (
    <div className="rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{title}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">
        {summary.ai_attributed}
        <span className="text-sm font-normal text-muted-foreground"> of {summary.total} from AI</span>
      </p>
      {platforms.length > 0 && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          {platforms.map(([name, n]) => `${name} ${n}`).join(" · ")}
        </p>
      )}
    </div>
  )
}

export function AttributionCard({
  clientId,
  initial,
}: {
  clientId: string
  initial: AttributionOverview
}) {
  const [overview, setOverview] = useState(initial)
  const [number, setNumber] = useState(initial.whatsapp_number ? `+${initial.whatsapp_number}` : "")
  const [message, setMessage] = useState(initial.whatsapp_message ?? "")
  const [enabled, setEnabled] = useState(initial.tracking_enabled)
  const [secret, setSecret] = useState<string | null>(null)
  const [answer, setAnswer] = useState("")
  const [eventType, setEventType] = useState<AnswerEventType>("lead")
  const [valueRm, setValueRm] = useState("")
  const [isPending, startTransition] = useTransition()

  function handleSave() {
    startTransition(async () => {
      try {
        const res = await updateAttributionAction(clientId, {
          whatsapp_number: number.trim() || null,
          whatsapp_message: message.trim() || null,
          tracking_enabled: enabled,
        })
        if ("error" in res) {
          toast.error(res.error)
          return
        }
        setOverview(res.overview)
        toast.success("Lead tracking saved")
      } catch {
        toast.error("Could not save lead tracking")
      }
    })
  }

  function handleRotate() {
    startTransition(async () => {
      try {
        const issued = await rotateWebhookSecretAction(clientId)
        setSecret(issued.webhook_secret)
        setOverview((o) => ({
          ...o,
          webhook_secret_set: true,
          webhook_secret_created_at: issued.webhook_secret_created_at,
        }))
        toast.success("New webhook secret generated. Copy it now, it won't be shown again")
      } catch {
        toast.error("Could not generate a webhook secret")
      }
    })
  }

  function handleLogAnswer() {
    if (!answer.trim()) return
    const value = Math.round((Number(valueRm) || 0) * 100)
    startTransition(async () => {
      try {
        const res = await logAnswerAction(clientId, {
          answer: answer.trim(),
          event_type: eventType,
          value_minor: Math.max(0, value),
        })
        setAnswer("")
        setValueRm("")
        toast.success(res.ai_attributed ? "Logged as an AI-attributed lead" : "Logged (not from AI)")
      } catch {
        toast.error("Could not log the answer")
      }
    })
  }

  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="flex items-center gap-2 text-sm font-medium">
        <MessageCircle className="h-4 w-4 text-primary" />
        Lead Tracking (WhatsApp + &ldquo;How did you hear about us?&rdquo;)
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Counts WhatsApp chats and leads that came from AI assistants. Matches show
        on the evidence ladder as attributed results, never as directly measured.
      </p>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <ChannelStat title={`WhatsApp clicks, last ${overview.window_days} days`} summary={overview.whatsapp_clicks} />
        <ChannelStat title={`"How did you hear" answers, last ${overview.window_days} days`} summary={overview.heard_about_us} />
      </div>

      {/* WhatsApp */}
      <div className="mt-4 space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">WhatsApp</p>
        <Label className="text-xs">Website snippet (paste before &lt;/body&gt;)</Label>
        <Textarea readOnly value={overview.website_snippet} rows={5} className="font-mono text-[11px]" />
        <Button type="button" variant="outline" size="sm" onClick={() => copy(overview.website_snippet, "Snippet")}>
          <Copy className="mr-1.5 h-3.5 w-3.5" /> Copy snippet
        </Button>
        <p className="text-xs text-muted-foreground">
          Keeps every WhatsApp button&apos;s own number and message. It remembers how
          the visitor first arrived (no cookies, no personal data) and counts the
          click as AI-attributed when that was ChatGPT, Perplexity, Gemini, Copilot or Claude.
        </p>

        <Label className="mt-2 block text-xs">Tracked link (Instagram bio, Google Business Profile, QR codes)</Label>
        <div className="flex gap-2">
          <Input readOnly value={overview.tracked_link_url} className="font-mono text-xs" />
          <Button type="button" variant="outline" size="icon" title="Copy link" onClick={() => copy(overview.tracked_link_url, "Link")}>
            <Copy className="h-4 w-4" />
          </Button>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <Label htmlFor="wa-number" className="text-xs">WhatsApp number for the tracked link</Label>
            <Input id="wa-number" placeholder="+60 12-345 6789" value={number} onChange={(e) => setNumber(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="wa-message" className="text-xs">Pre-filled message (optional)</Label>
            <Input id="wa-message" placeholder="Hi, I'd like to ask about…" value={message} onChange={(e) => setMessage(e.target.value)} />
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs">
          <Checkbox checked={enabled} onCheckedChange={(v) => setEnabled(v === true)} />
          Tracking on (when off, links still work but nothing is counted)
        </label>
        <Button type="button" size="sm" onClick={handleSave} disabled={isPending}>Save</Button>
      </div>

      {/* Webhook */}
      <div className="mt-5 space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          &ldquo;How did you hear about us?&rdquo; webhook
        </p>
        <p className="text-xs text-muted-foreground">
          Point the client&apos;s enquiry or booking form (Zapier, Make, Typeform, CRM) at this
          URL. Send the secret in an <code>X-SeenBy-Secret</code> header. Retries with the
          same <code>submission_id</code> are ignored.
        </p>
        <div className="flex gap-2">
          <Input readOnly value={overview.webhook_url} className="font-mono text-xs" />
          <Button type="button" variant="outline" size="icon" title="Copy URL" onClick={() => copy(overview.webhook_url, "Webhook URL")}>
            <Copy className="h-4 w-4" />
          </Button>
        </div>
        {secret && (
          <div className="flex gap-2">
            <Input readOnly value={secret} className="font-mono text-xs" />
            <Button type="button" variant="outline" size="icon" title="Copy secret" onClick={() => copy(secret, "Secret")}>
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          {overview.webhook_secret_set && overview.webhook_secret_created_at
            ? `Secret set ${timeAgo(overview.webhook_secret_created_at)}. Generating a new one stops the old one working.`
            : "No secret yet."}
        </p>
        <Button type="button" variant="outline" size="sm" onClick={handleRotate} disabled={isPending}>
          <KeyRound className="mr-1.5 h-3.5 w-3.5" />
          {overview.webhook_secret_set ? "Generate new secret" : "Generate secret"}
        </Button>
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Example body</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-muted p-2 font-mono text-[11px]">{examplePayload()}</pre>
        </details>
      </div>

      {/* Manual entry */}
      <div className="mt-5 space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Log an answer by hand</p>
        <p className="text-xs text-muted-foreground">For answers the client&apos;s staff collect on the phone or at the counter.</p>
        <div className="grid gap-2 sm:grid-cols-[1fr_140px_110px]">
          <Input placeholder='What they said, e.g. "ChatGPT"' value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={500} />
          <Select value={eventType} onValueChange={(v) => setEventType(v as AnswerEventType)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {EVENT_TYPES.map((t) => (
                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input inputMode="decimal" placeholder="Value RM" value={valueRm} onChange={(e) => setValueRm(e.target.value)} />
        </div>
        <Button type="button" variant="outline" size="sm" onClick={handleLogAnswer} disabled={isPending || !answer.trim()}>
          <Plus className="mr-1.5 h-3.5 w-3.5" /> Log answer
        </Button>
      </div>

      {overview.recent.length > 0 && (
        <div className="mt-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Recent</p>
          <ul className="mt-1 divide-y text-xs">
            {overview.recent.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 py-1.5">
                <span className="min-w-0 truncate">
                  {s.channel === "whatsapp_click" ? "WhatsApp click" : "Answer"}
                  {s.ai_platform ? (
                    <span className="font-medium text-foreground"> · {s.ai_platform}</span>
                  ) : (
                    <span className="text-muted-foreground"> · not from AI</span>
                  )}
                  {s.raw_value && (
                    <span className="text-muted-foreground">
                      {" "}({s.match_reason ? MATCH_LABELS[s.match_reason] : s.channel === "whatsapp_click" ? "arrived from" : "said"} &ldquo;{s.raw_value}&rdquo;)
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-muted-foreground">{timeAgo(s.occurred_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
