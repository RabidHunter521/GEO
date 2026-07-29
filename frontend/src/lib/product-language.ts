export const PRODUCT_LANGUAGE = {
  readiness: "Growth Readiness",
  presence: "AI Presence",
  accuracy: "Accuracy",
  businessImpact: "Business Impact",
} as const

export type EvidenceLevel =
  | "observed"
  | "attributed"
  | "assisted"
  | "estimated"

const EVIDENCE_LABELS: Record<EvidenceLevel, string> = {
  observed: "Observed",
  attributed: "Attributed",
  assisted: "Assisted",
  estimated: "Estimated",
}

export function evidenceLabel(level: EvidenceLevel): string {
  return EVIDENCE_LABELS[level]
}
