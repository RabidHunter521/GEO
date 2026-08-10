import { PRODUCT_LANGUAGE } from "@/lib/product-language"

export type ActivityTone =
  | "success"
  | "warning"
  | "danger"
  | "information"
  | "neutral"

export interface ActivityPresentation {
  label: string
  tone: ActivityTone
}

const ACTIVITY_PRESENTATION: Record<string, ActivityPresentation> = {
  scan_completed: { label: "Visibility scan completed", tone: "success" },
  scan_failed: { label: "Visibility scan needs attention", tone: "danger" },
  toolkit_generated: { label: "Technical files prepared", tone: "information" },
  toolkit_verified: { label: "Technical files checked", tone: "success" },
  client_created: { label: "Client onboarded", tone: "neutral" },
  digest_sent: { label: "Weekly update sent", tone: "information" },
  report_generated: { label: "Monthly report prepared", tone: "information" },
  report_sent: { label: "Monthly report delivered", tone: "success" },
  alert_sent: { label: "Visibility alert sent", tone: "warning" },
  hallucination_flagged: { label: "Potential accuracy issue found", tone: "warning" },
  content_analyzed: { label: "Content opportunities analyzed", tone: "information" },
  authority_assets_added: { label: "Authority opportunities added", tone: "information" },
  authority_status_changed: { label: "Authority work updated", tone: "information" },
  brief_generated: { label: "Content brief prepared", tone: "information" },
  deliverable_generated: { label: "Content deliverable prepared", tone: "information" },
  traffic_updated: { label: "AI traffic data updated", tone: "information" },
  page_audit_run: { label: "Page citability checked", tone: "information" },
  site_audit_run: { label: "Website readiness checked", tone: "information" },
  citation_flip: { label: "Share-of-source change", tone: "information" },
}

const ACTIVITY_NOTE_REPLACEMENTS: ReadonlyArray<readonly [RegExp, string]> = [
  [/\boverall GEO score\b/gi, PRODUCT_LANGUAGE.readiness],
  [/\bAI visibility score\b/gi, PRODUCT_LANGUAGE.readiness],
  [/\boverall score\b/gi, PRODUCT_LANGUAGE.readiness],
  [/\bGEO score\b/gi, PRODUCT_LANGUAGE.readiness],
  [/\bfirst mentioned\b/gi, "first seen by AI"],
  [/\bnot mentioned\b/gi, "not seen by AI"],
  [/\buncited\b/gi, "not seen by AI"],
  [/\bmentioned\b/gi, "seen by AI"],
  [/\bcited\b/gi, "seen by AI"],
  [/\bcitation rate\b/gi, "visibility frequency"],
  [/\branking position\b/gi, "AI Search Ranking"],
  [/\bvisibility gap\b/gi, "Your competitors are winning here"],
  [/\bconfidence score\b/gi, "internal review signal"],
  [/\bchar offset\b/gi, "internal metadata"],
  [/\btoken count\b/gi, "internal metadata"],
]

function humanize(eventType: string): string {
  const words = eventType.replaceAll("_", " ").trim()
  if (!words) return "Activity updated"
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function presentActivityType(eventType: string): ActivityPresentation {
  return ACTIVITY_PRESENTATION[eventType] ?? {
    label: humanize(eventType),
    tone: "neutral",
  }
}

export function presentActivityNote(note: string): string {
  return ACTIVITY_NOTE_REPLACEMENTS.reduce(
    (presented, [pattern, replacement]) => presented.replace(pattern, replacement),
    note,
  )
}
