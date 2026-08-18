// frontend/src/lib/api.ts
// SERVER-ONLY: Do not import this file from client components ("use client").
// Accesses process.env.ADMIN_API_KEY which is a server-side env var.
//
// The import below turns that from a convention into a BUILD ERROR: if this
// module is ever pulled into a client bundle, the build fails instead of
// silently shipping a module that reaches for admin credentials.
import "server-only"
import type { CausalityResponse, Client, ClientListItem, Competitor, ControlQuery, Ga4SyncReport, GeoScore, Guarantee, GuaranteeProgress, ToolkitFiles, VerificationResult, CompetitorIntelligenceResponse, ActivityLogEntry, Report, Scan, ContentAnalysis, ContentRoadmap, ActionRecommendation, AiTrafficSnapshot, ShareTokenResponse, WinLossResponse, ContentBrief, CompetitorTrendsResponse, IndustryBenchmark, ScanDiffResponse, GapMatrixResponse, RemediationItem, RemediationStatus, DimensionAssessment, AssessmentDimension, ShareOfSource, ShareOfSourceHistoryPoint, CompetitorAIReadiness, SiteAudit, SiteAuditLatest, CompetitorSiteAudit, PageAudit, PageAuditListItem, ContentDeliverable, DeliverableType, AuthorityView, AuthorityCatalogItem, AuthorityAsset, AuthorityStatus, AuthorityVerifyResponse, AddAuthorityAssetItem, WorkLogEntry, WorkLogCategory, WorkLogStatus, WorkLogSuggestion, MisinformationFinding, MisinformationQueue, CommandCenter, OutcomeAction, OutcomeActionCreate, OutcomeActionListResponse, OutcomeActionPatch, OutcomeActionStatus, BusinessLocation, BusinessLocationInput, TruthFact, TruthFactDraftInput, TruthFactListResponse, TruthFactVersion, QueryStabilityEntry, ImpactSummary, BenchmarkComparison, DashboardFeedResponse, DashboardFilters, DashboardSummary } from "@/types"

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

function apiHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${process.env.ADMIN_API_KEY}`,
  }
}

// Carries the HTTP status (so callers can branch on it, e.g. 409 = scan running)
// while its message is the backend's own `detail` when one is available — so a
// 422 surfaces "contact_email: value is not a valid email", not a bare code.
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail?: string,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

// Pulls a human message out of a FastAPI error body: `detail` is a string for
// HTTPException and a list of {loc, msg} for 422 validation errors.
async function extractDetail(res: Response): Promise<string | undefined> {
  try {
    const body = await res.json()
    const detail = body?.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
      return detail
        .map((e) => {
          const loc = Array.isArray(e?.loc)
            ? e.loc.filter((p: unknown) => p !== "body").join(".")
            : ""
          return loc && e?.msg ? `${loc}: ${e.msg}` : e?.msg
        })
        .filter(Boolean)
        .join("; ")
    }
  } catch {
    // non-JSON (or empty) error body — fall back to the status line
  }
  return undefined
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...apiHeaders(), ...init?.headers },
    cache: "no-store",
  })
  if (res.status === 204) return undefined as T
  if (!res.ok) {
    const detail = await extractDetail(res)
    const statusLine = `API ${init?.method ?? "GET"} ${path} → ${res.status}`
    throw new ApiError(res.status, detail ?? statusLine, detail)
  }
  return res.json() as Promise<T>
}

// ── Clients ──────────────────────────────────────────────────────────────────

export function getClients(): Promise<ClientListItem[]> {
  return apiFetch<ClientListItem[]>("/api/v1/clients")
}

export function getClient(id: string): Promise<Client> {
  return apiFetch<Client>(`/api/v1/clients/${id}`)
}

export function createClient(
  body: Pick<Client, "name" | "website" | "industry"> &
    Partial<Pick<Client, "is_prospect" | "enabled_platforms">>,
): Promise<Client> {
  return apiFetch<Client>("/api/v1/clients", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function updateClient(
  id: string,
  body: Partial<
    Pick<
      Client,
      | "name"
      | "website"
      | "industry"
      | "description"
      | "target_audience"
      | "city"
      | "state"
      | "country"
      | "phone"
      | "contact_email"
      | "brand_authority_score"
      | "brand_authority_evidence"
      | "content_quality_score"
      | "content_quality_evidence"
      | "score_drop_threshold"
      | "scan_cadence_days"
      | "avg_deal_value_rm"
      | "visitor_to_lead_pct"
      | "lead_to_customer_pct"
      | "enabled_platforms"
      | "is_prospect"
      | "internal_notes"
      | "ga4_property_id"
      | "benchmark_opt_out"
    >
  >,
): Promise<Client> {
  return apiFetch<Client>(`/api/v1/clients/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export function deleteClient(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/clients/${id}`, { method: "DELETE" })
}

export async function uploadClientLogo(id: string, formData: FormData): Promise<Client> {
  // Multipart upload — must NOT set Content-Type (fetch sets the boundary).
  const res = await fetch(`${BASE}/api/v1/clients/${id}/logo`, {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.ADMIN_API_KEY}` },
    body: formData,
    cache: "no-store",
  })
  if (!res.ok) {
    let detail = "Logo upload failed"
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(detail)
  }
  return res.json() as Promise<Client>
}

export function getGapMatrix(): Promise<GapMatrixResponse> {
  return apiFetch<GapMatrixResponse>(`/api/v1/clients/gap-matrix`)
}

export function getLatestGeoScore(clientId: string): Promise<GeoScore | null> {
  return apiFetch<GeoScore | null>(`/api/v1/clients/${clientId}/geo-score/latest`)
}

export function getCommandCenter(clientId: string): Promise<CommandCenter> {
  return apiFetch<CommandCenter>(`/api/v1/clients/${clientId}/command-center`)
}

export function generateShareToken(clientId: string): Promise<ShareTokenResponse> {
  return apiFetch<ShareTokenResponse>(`/api/v1/clients/${clientId}/share-token`, {
    method: "POST",
  })
}

export function revokeShareToken(clientId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/clients/${clientId}/share-token`, {
    method: "DELETE",
  })
}

// ── Competitors ───────────────────────────────────────────────────────────────

export function getCompetitors(clientId: string): Promise<Competitor[]> {
  return apiFetch<Competitor[]>(`/api/v1/clients/${clientId}/competitors`)
}

export function addCompetitor(
  clientId: string,
  body: Pick<Competitor, "name"> & { website?: string },
): Promise<Competitor> {
  return apiFetch<Competitor>(`/api/v1/clients/${clientId}/competitors`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function deleteCompetitor(
  clientId: string,
  competitorId: string,
): Promise<void> {
  return apiFetch<void>(`/api/v1/clients/${clientId}/competitors/${competitorId}`, {
    method: "DELETE",
  })
}

export function getCausality(clientId: string): Promise<CausalityResponse> {
  return apiFetch<CausalityResponse>(`/api/v1/scans/client/${clientId}/causality`)
}

// ── Guarantee ────────────────────────────────────────────────────────────────

export function getGuarantee(clientId: string): Promise<GuaranteeProgress | null> {
  return apiFetch<GuaranteeProgress | null>(`/api/v1/clients/${clientId}/guarantee`)
}

export function createGuarantee(
  clientId: string,
  body: {
    metric?: string
    target_value: number
    deadline_date: string
    baseline_override?: number | null
    start_date?: string | null
  },
): Promise<Guarantee> {
  return apiFetch<Guarantee>(`/api/v1/clients/${clientId}/guarantee`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function resolveGuarantee(
  clientId: string,
  guaranteeId: string,
  body: { outcome: "met" | "missed" | "void"; note?: string },
): Promise<Guarantee> {
  return apiFetch<Guarantee>(
    `/api/v1/clients/${clientId}/guarantee/${guaranteeId}/resolve`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

// ── Control (benchmark) queries ──────────────────────────────────────────────

export function getControlQueries(clientId: string): Promise<ControlQuery[]> {
  return apiFetch<ControlQuery[]>(`/api/v1/clients/${clientId}/control-queries`)
}

export function createControlQuery(
  clientId: string,
  body: { query_text: string; category?: string },
): Promise<ControlQuery> {
  return apiFetch<ControlQuery>(`/api/v1/clients/${clientId}/control-queries`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function updateControlQuery(
  clientId: string,
  controlQueryId: string,
  body: { active: boolean },
): Promise<ControlQuery> {
  return apiFetch<ControlQuery>(
    `/api/v1/clients/${clientId}/control-queries/${controlQueryId}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  )
}

export function getCompetitorIntelligence(clientId: string): Promise<CompetitorIntelligenceResponse> {
  return apiFetch<CompetitorIntelligenceResponse>(
    `/api/v1/clients/${clientId}/competitors/intelligence`,
  )
}

export function getWinLoss(clientId: string): Promise<WinLossResponse> {
  return apiFetch<WinLossResponse>(`/api/v1/clients/${clientId}/competitors/win-loss`)
}

export function generateContentBrief(clientId: string, resultId: string): Promise<ContentBrief> {
  return apiFetch<ContentBrief>(
    `/api/v1/clients/${clientId}/competitors/win-loss/${resultId}/brief`,
    { method: "POST" },
  )
}

export function getCompetitorTrends(clientId: string): Promise<CompetitorTrendsResponse> {
  return apiFetch<CompetitorTrendsResponse>(`/api/v1/clients/${clientId}/competitors/trends`)
}

export function getProvenance(clientId: string): Promise<ShareOfSource> {
  return apiFetch<ShareOfSource>(`/api/v1/clients/${clientId}/competitors/provenance`)
}

export function getShareOfSourceHistory(clientId: string): Promise<ShareOfSourceHistoryPoint[]> {
  return apiFetch<ShareOfSourceHistoryPoint[]>(`/api/v1/clients/${clientId}/competitors/provenance/history`)
}

// Live outbound check against the client's + competitors' sites — called
// on-demand from a button, never on page load.
export function getAIReadiness(clientId: string): Promise<CompetitorAIReadiness> {
  return apiFetch<CompetitorAIReadiness>(`/api/v1/clients/${clientId}/competitors/ai-readiness`)
}

export function getIndustryBenchmark(clientId: string): Promise<IndustryBenchmark | null> {
  return apiFetch<IndustryBenchmark | null>(`/api/v1/clients/${clientId}/benchmark`)
}

export function getActivityLog(clientId: string, limit = 50, skip = 0): Promise<ActivityLogEntry[]> {
  return apiFetch<ActivityLogEntry[]>(
    `/api/v1/clients/${clientId}/activity?limit=${limit}&skip=${skip}`,
  )
}

// ── Work log ─────────────────────────────────────────────────────────────────

export async function getWorkLog(
  clientId: string, status?: WorkLogStatus,
): Promise<WorkLogEntry[]> {
  const q = status ? `?status=${status}` : ""
  return apiFetch<WorkLogEntry[]>(`/api/v1/clients/${clientId}/work-log${q}`)
}
export async function createWorkLogEntry(
  clientId: string, body: { category: WorkLogCategory; description: string; entry_date: string },
): Promise<WorkLogEntry> {
  return apiFetch<WorkLogEntry>(`/api/v1/clients/${clientId}/work-log`, {
    method: "POST", body: JSON.stringify(body),
  })
}
export async function patchWorkLogEntry(
  clientId: string, entryId: string,
  patch: { category?: WorkLogCategory; description?: string; entry_date?: string; status?: WorkLogStatus },
): Promise<WorkLogEntry> {
  return apiFetch<WorkLogEntry>(`/api/v1/clients/${clientId}/work-log/${entryId}`, {
    method: "PATCH", body: JSON.stringify(patch),
  })
}

export async function getSuggestedWorkLog(): Promise<WorkLogSuggestion[]> {
  return apiFetch<WorkLogSuggestion[]>("/api/v1/work-log/suggested")
}

export async function getSuggestedWorkLogCount(): Promise<number> {
  const res = await apiFetch<{ count: number }>("/api/v1/work-log/suggested/count")
  return res.count
}

// â”€â”€ Outcome Actions â”€â”€
export function getOutcomeActions(
  clientId: string,
  options?: { status?: OutcomeActionStatus; due_from?: string; due_to?: string; page?: number; page_size?: number },
): Promise<OutcomeActionListResponse> {
  const params = new URLSearchParams()
  if (options?.status) params.set("status", options.status)
  if (options?.due_from) params.set("due_from", options.due_from)
  if (options?.due_to) params.set("due_to", options.due_to)
  if (options?.page) params.set("page", String(options.page))
  if (options?.page_size) params.set("page_size", String(options.page_size))
  const query = params.size ? `?${params}` : ""
  return apiFetch<OutcomeActionListResponse>(`/api/v1/clients/${clientId}/outcome-actions${query}`)
}

export async function getAllOutcomeActions(
  clientId: string,
  options?: { status?: OutcomeActionStatus; due_from?: string; due_to?: string },
): Promise<OutcomeAction[]> {
  const pageSize = 100
  const actions: OutcomeAction[] = []
  let page = 1
  let total = Number.POSITIVE_INFINITY

  while (actions.length < total) {
    const response = await getOutcomeActions(clientId, { ...options, page, page_size: pageSize })
    actions.push(...response.actions)
    total = response.total
    if (response.actions.length === 0) break
    page += 1
  }

  return actions
}

export function getOutcomeAction(clientId: string, actionId: string): Promise<OutcomeAction> {
  return apiFetch<OutcomeAction>(`/api/v1/clients/${clientId}/outcome-actions/${actionId}`)
}

export function createOutcomeAction(clientId: string, body: OutcomeActionCreate): Promise<OutcomeAction> {
  return apiFetch<OutcomeAction>(`/api/v1/clients/${clientId}/outcome-actions`, {
    method: "POST", body: JSON.stringify(body),
  })
}

export function patchOutcomeAction(
  clientId: string, actionId: string, body: OutcomeActionPatch,
): Promise<OutcomeAction> {
  return apiFetch<OutcomeAction>(`/api/v1/clients/${clientId}/outcome-actions/${actionId}`, {
    method: "PATCH", body: JSON.stringify(body),
  })
}

export function transitionOutcomeAction(
  clientId: string, actionId: string, status: OutcomeActionStatus,
): Promise<OutcomeAction> {
  return apiFetch<OutcomeAction>(`/api/v1/clients/${clientId}/outcome-actions/${actionId}/transition`, {
    method: "POST", body: JSON.stringify({ status }),
  })
}

export function getOutcomeActionReviewQueue(options?: { page?: number; page_size?: number }): Promise<OutcomeActionListResponse> {
  const params = new URLSearchParams()
  if (options?.page) params.set("page", String(options.page))
  if (options?.page_size) params.set("page_size", String(options.page_size))
  const query = params.size ? `?${params}` : ""
  return apiFetch<OutcomeActionListResponse>(`/api/v1/outcome-actions/review-queue${query}`)
}

// â”€â”€ Business locations and Truth Vault (admin only) â”€â”€

export function getBusinessLocations(clientId: string, active = true): Promise<BusinessLocation[]> {
  return apiFetch<BusinessLocation[]>(`/api/v1/clients/${clientId}/locations?active=${active}`)
}

export function createBusinessLocation(
  clientId: string, body: Required<Pick<BusinessLocationInput, "name">> & BusinessLocationInput,
): Promise<BusinessLocation> {
  return apiFetch<BusinessLocation>(`/api/v1/clients/${clientId}/locations`, {
    method: "POST", body: JSON.stringify(body),
  })
}

export function patchBusinessLocation(
  clientId: string, locationId: string, body: BusinessLocationInput,
): Promise<BusinessLocation> {
  return apiFetch<BusinessLocation>(`/api/v1/clients/${clientId}/locations/${locationId}`, {
    method: "PATCH", body: JSON.stringify(body),
  })
}

export function deactivateBusinessLocation(
  clientId: string, locationId: string, replacementLocationId?: string,
): Promise<void> {
  return apiFetch<void>(`/api/v1/clients/${clientId}/locations/${locationId}`, {
    method: "DELETE",
    body: replacementLocationId ? JSON.stringify({ replacement_location_id: replacementLocationId }) : undefined,
  })
}

export function getTruthFacts(
  clientId: string,
  options?: { location_id?: string; mode?: "current" | "history"; page?: number; page_size?: number },
): Promise<TruthFactListResponse> {
  const params = new URLSearchParams()
  if (options?.location_id) params.set("location_id", options.location_id)
  if (options?.mode) params.set("mode", options.mode)
  if (options?.page) params.set("page", String(options.page))
  if (options?.page_size) params.set("page_size", String(options.page_size))
  const query = params.size ? `?${params}` : ""
  return apiFetch<TruthFactListResponse>(`/api/v1/clients/${clientId}/truth-facts${query}`)
}

// History responses are paginated at 100 rows by the API. The Truth Vault
// administration page needs the complete scope so every existing fact remains
// reviewable, not just the first page.
export async function getAllTruthFacts(
  clientId: string,
  options?: Omit<NonNullable<Parameters<typeof getTruthFacts>[1]>, "page" | "page_size">,
): Promise<TruthFact[]> {
  const facts: TruthFact[] = []
  let page = 1
  let total = Number.POSITIVE_INFINITY

  while (facts.length < total) {
    const result = await getTruthFacts(clientId, { ...options, page, page_size: 100 })
    facts.push(...result.facts)
    total = result.total
    if (result.facts.length === 0) break
    page += 1
  }

  return facts
}

export function createTruthFact(
  clientId: string, body: Pick<TruthFact, "fact_type" | "fact_key" | "location_id">,
): Promise<TruthFact> {
  return apiFetch<TruthFact>(`/api/v1/clients/${clientId}/truth-facts`, {
    method: "POST", body: JSON.stringify(body),
  })
}

export function draftTruthFactVersion(
  clientId: string, factId: string, body: TruthFactDraftInput,
): Promise<TruthFactVersion> {
  return apiFetch<TruthFactVersion>(`/api/v1/clients/${clientId}/truth-facts/${factId}/versions`, {
    method: "POST", body: JSON.stringify(body),
  })
}

export function approveTruthFactVersion(
  clientId: string, factId: string, versionId: string, approvedBy: string,
): Promise<TruthFactVersion> {
  return apiFetch<TruthFactVersion>(
    `/api/v1/clients/${clientId}/truth-facts/${factId}/approve/${versionId}`,
    { method: "POST", body: JSON.stringify({ approved_by: approvedBy }) },
  )
}

export function retireTruthFact(clientId: string, factId: string, effectiveAt: string): Promise<TruthFactVersion> {
  return apiFetch<TruthFactVersion>(`/api/v1/clients/${clientId}/truth-facts/${factId}/retire`, {
    method: "POST", body: JSON.stringify({ effective_at: effectiveAt }),
  })
}

// ── Toolkit ───────────────────────────────────────────────────────────────────

export function getToolkitFiles(clientId: string): Promise<ToolkitFiles | null> {
  return apiFetch<ToolkitFiles | null>(`/api/v1/clients/${clientId}/toolkit/files`)
}

export function generateToolkitFiles(clientId: string): Promise<ToolkitFiles> {
  return apiFetch<ToolkitFiles>(`/api/v1/clients/${clientId}/toolkit/generate`, {
    method: "POST",
  })
}

export function verifyToolkitFiles(clientId: string): Promise<VerificationResult> {
  return apiFetch<VerificationResult>(`/api/v1/clients/${clientId}/toolkit/verify`, {
    method: "POST",
  })
}

export function generateLlmsFullTxt(clientId: string): Promise<ToolkitFiles> {
  return apiFetch<ToolkitFiles>(`/api/v1/clients/${clientId}/toolkit/generate-llms-full`, {
    method: "POST",
  })
}

// ── Site AI-Readiness Audit ──────────────────────────────────────────────────

export function runSiteAudit(clientId: string): Promise<SiteAudit> {
  return apiFetch<SiteAudit>(`/api/v1/clients/${clientId}/site-audit`, { method: "POST" })
}

export function getLatestSiteAudit(clientId: string): Promise<SiteAuditLatest | null> {
  return apiFetch<SiteAuditLatest | null>(`/api/v1/clients/${clientId}/site-audit/latest`)
}

// Live outbound check of a competitor site — never persisted.
export function runCompetitorSiteAudit(
  clientId: string,
  competitorId: string,
): Promise<CompetitorSiteAudit> {
  return apiFetch<CompetitorSiteAudit>(
    `/api/v1/clients/${clientId}/site-audit/competitor/${competitorId}`,
    { method: "POST" },
  )
}

// ── Content Gaps ────────────────────────────────────────────────────────────────

export function getContentGaps(clientId: string): Promise<ContentAnalysis | null> {
  return apiFetch<ContentAnalysis | null>(`/api/v1/clients/${clientId}/content-gaps`)
}

export function runContentAnalysis(clientId: string): Promise<ContentAnalysis> {
  return apiFetch<ContentAnalysis>(`/api/v1/clients/${clientId}/content-gaps/analyze`, {
    method: "POST",
  })
}

// ── Content Roadmap ─────────────────────────────────────────────────────────────

export function getContentRoadmap(clientId: string): Promise<ContentRoadmap | null> {
  return apiFetch<ContentRoadmap | null>(`/api/v1/clients/${clientId}/content-roadmap`)
}

export function generateContentRoadmap(clientId: string): Promise<ContentRoadmap> {
  return apiFetch<ContentRoadmap>(`/api/v1/clients/${clientId}/content-roadmap/generate`, {
    method: "POST",
  })
}

export function generateRoadmapItemContent(
  clientId: string,
  roadmapId: string,
  itemIndex: number,
): Promise<ContentRoadmap> {
  return apiFetch<ContentRoadmap>(
    `/api/v1/clients/${clientId}/content-roadmap/${roadmapId}/items/${itemIndex}/content`,
    { method: "POST" },
  )
}

// ── Action Center ─────────────────────────────────────────────────────────────

export function getActionRecommendations(clientId: string): Promise<ActionRecommendation[]> {
  return apiFetch<ActionRecommendation[]>(`/api/v1/clients/${clientId}/actions`)
}

export function updateActionStatus(
  clientId: string,
  actionId: string,
  status: "done" | "dismissed",
): Promise<ActionRecommendation> {
  return apiFetch<ActionRecommendation>(`/api/v1/clients/${clientId}/actions/${actionId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  })
}

// ── AI Referral Traffic ─────────────────────────────────────────────────────────

export function getTrafficHistory(clientId: string): Promise<AiTrafficSnapshot[]> {
  return apiFetch<AiTrafficSnapshot[]>(`/api/v1/clients/${clientId}/traffic`)
}

export function upsertTrafficSnapshot(
  clientId: string,
  body: { period: string; ai_visitors: number },
): Promise<AiTrafficSnapshot> {
  return apiFetch<AiTrafficSnapshot>(`/api/v1/clients/${clientId}/traffic`, {
    method: "PUT",
    body: JSON.stringify(body),
  })
}

export function syncGa4Traffic(clientId: string): Promise<Ga4SyncReport> {
  return apiFetch<Ga4SyncReport>(`/api/v1/clients/${clientId}/traffic/sync`, {
    method: "POST",
  })
}

// ── Reports ───────────────────────────────────────────────────────────────────

export function getReports(clientId: string): Promise<Report[]> {
  return apiFetch<Report[]>(`/api/v1/clients/${clientId}/reports`)
}

export function generateReport(clientId: string): Promise<{ task_id: string; client_id: string; status: string }> {
  return apiFetch<{ task_id: string; client_id: string; status: string }>(
    `/api/v1/clients/${clientId}/reports/generate`,
    { method: "POST" },
  )
}

export function sendReport(clientId: string, reportId: string): Promise<{ sent: boolean; report_id: string }> {
  return apiFetch<{ sent: boolean; report_id: string }>(
    `/api/v1/clients/${clientId}/reports/${reportId}/send`,
    { method: "POST" },
  )
}

// ── Scans ─────────────────────────────────────────────────────────────────────

export function getLatestScan(clientId: string): Promise<Scan | null> {
  return apiFetch<Scan | null>(`/api/v1/scans/client/${clientId}/latest`)
}

export function triggerScan(clientId: string): Promise<{ id: string; status: string }> {
  return apiFetch<{ id: string; status: string }>("/api/v1/scans/", {
    method: "POST",
    body: JSON.stringify({ client_id: clientId }),
  })
}

export function flagHallucination(
  scanId: string,
  resultId: string,
): Promise<{ flagged: boolean; result_id: string }> {
  return apiFetch<{ flagged: boolean; result_id: string }>(
    `/api/v1/scans/${scanId}/results/${resultId}/flag-hallucination`,
    { method: "POST" },
  )
}

export function getScanDiff(clientId: string): Promise<ScanDiffResponse> {
  return apiFetch<ScanDiffResponse>(`/api/v1/scans/client/${clientId}/diff`)
}

// --- Remediation loop (admin) ------------------------------------------------

export function listRemediation(clientId: string): Promise<RemediationItem[]> {
  return apiFetch<RemediationItem[]>(`/api/v1/clients/${clientId}/remediation`)
}

export function syncRemediation(clientId: string): Promise<RemediationItem[]> {
  return apiFetch<RemediationItem[]>(`/api/v1/clients/${clientId}/remediation/sync`, {
    method: "POST",
  })
}

export function updateRemediationStatus(
  clientId: string,
  itemId: string,
  status: RemediationStatus,
): Promise<RemediationItem> {
  return apiFetch<RemediationItem>(
    `/api/v1/clients/${clientId}/remediation/${itemId}`,
    { method: "PATCH", body: JSON.stringify({ status }) },
  )
}

// --- AI misinformation compliance (admin only) -------------------------------

export function listMisinformation(clientId: string): Promise<MisinformationQueue> {
  return apiFetch<MisinformationQueue>(`/api/v1/clients/${clientId}/misinformation`)
}

export function reviewMisinformation(
  clientId: string,
  findingId: string,
  action: "confirm" | "dismiss",
  note?: string,
): Promise<MisinformationFinding> {
  return apiFetch<MisinformationFinding>(
    `/api/v1/clients/${clientId}/misinformation/${findingId}/review`,
    { method: "POST", body: JSON.stringify({ action, note: note ?? null }) },
  )
}

export function markMisinformationCorrected(
  clientId: string,
  findingId: string,
): Promise<MisinformationFinding> {
  return apiFetch<MisinformationFinding>(
    `/api/v1/clients/${clientId}/misinformation/${findingId}/corrected`,
    { method: "POST" },
  )
}

export function resolveMisinformation(
  clientId: string,
  findingId: string,
): Promise<MisinformationFinding> {
  return apiFetch<MisinformationFinding>(
    `/api/v1/clients/${clientId}/misinformation/${findingId}/resolve`,
    { method: "POST" },
  )
}

// ── Dimension Assessment ───────────────────────────────────────────────────────

export function generateAssessment(
  clientId: string,
  dimension: AssessmentDimension,
): Promise<DimensionAssessment> {
  return apiFetch<DimensionAssessment>(
    `/api/v1/clients/${clientId}/assessments/${dimension}/generate`,
    { method: "POST" },
  )
}

export function acceptAssessment(
  clientId: string,
  dimension: AssessmentDimension,
  finalScore: number | null,
): Promise<DimensionAssessment> {
  return apiFetch<DimensionAssessment>(
    `/api/v1/clients/${clientId}/assessments/${dimension}/accept`,
    { method: "POST", body: JSON.stringify({ final_score: finalScore }) },
  )
}

// ── Content Studio ───────────────────────────────────────────────────────────

export function runPageAudit(clientId: string, url: string): Promise<PageAudit> {
  return apiFetch<PageAudit>(`/api/v1/clients/${clientId}/page-audits`, {
    method: "POST",
    body: JSON.stringify({ url }),
  })
}

export function getPageAudits(clientId: string): Promise<PageAuditListItem[]> {
  return apiFetch<PageAuditListItem[]>(`/api/v1/clients/${clientId}/page-audits`)
}

export function getPageAudit(clientId: string, auditId: string): Promise<PageAudit> {
  return apiFetch<PageAudit>(`/api/v1/clients/${clientId}/page-audits/${auditId}`)
}

export function generateDeliverable(
  clientId: string,
  type: DeliverableType,
  competitorId?: string,
): Promise<ContentDeliverable> {
  return apiFetch<ContentDeliverable>(`/api/v1/clients/${clientId}/deliverables`, {
    method: "POST",
    body: JSON.stringify({ type, competitor_id: competitorId ?? null }),
  })
}

export function getDeliverables(clientId: string): Promise<ContentDeliverable[]> {
  return apiFetch<ContentDeliverable[]>(`/api/v1/clients/${clientId}/deliverables`)
}

export function updateDeliverable(
  clientId: string,
  deliverableId: string,
  patch: { title?: string; body_md?: string; status?: "reviewed" },
): Promise<ContentDeliverable> {
  return apiFetch<ContentDeliverable>(
    `/api/v1/clients/${clientId}/deliverables/${deliverableId}`,
    { method: "PATCH", body: JSON.stringify(patch) },
  )
}

export async function getAuthorityView(clientId: string): Promise<AuthorityView> {
  return apiFetch<AuthorityView>(`/api/v1/clients/${clientId}/authority`)
}
export async function getAuthorityCatalog(clientId: string): Promise<AuthorityCatalogItem[]> {
  return apiFetch<AuthorityCatalogItem[]>(`/api/v1/clients/${clientId}/authority/catalog`)
}
export async function addAuthorityAssets(
  clientId: string, items: AddAuthorityAssetItem[],
): Promise<AuthorityAsset[]> {
  return apiFetch<AuthorityAsset[]>(`/api/v1/clients/${clientId}/authority`, {
    method: "POST", body: JSON.stringify({ items }),
  })
}
export async function patchAuthorityAsset(
  clientId: string, assetId: string,
  patch: { status?: AuthorityStatus; url?: string; notes?: string; hidden?: boolean },
): Promise<AuthorityAsset> {
  return apiFetch<AuthorityAsset>(`/api/v1/clients/${clientId}/authority/${assetId}`, {
    method: "PATCH", body: JSON.stringify(patch),
  })
}
export async function verifyAuthorityAsset(
  clientId: string, assetId: string,
): Promise<AuthorityVerifyResponse> {
  return apiFetch<AuthorityVerifyResponse>(
    `/api/v1/clients/${clientId}/authority/${assetId}/verify`, { method: "POST" },
  )
}
export async function addAuthorityReviewSnapshot(
  clientId: string, assetId: string, rating: number, count: number,
): Promise<AuthorityAsset> {
  return apiFetch<AuthorityAsset>(
    `/api/v1/clients/${clientId}/authority/${assetId}/review-snapshot`,
    { method: "POST", body: JSON.stringify({ rating, count }) },
  )
}

// ── Query Stability (Phase 5) ────────────────────────────────────────────

export function getQueryStability(clientId: string): Promise<QueryStabilityEntry[]> {
  return apiFetch<QueryStabilityEntry[]>(`/api/v1/clients/${clientId}/query-stability`)
}

// ── Business Impact (Phase 5) ────────────────────────────────────────────

export function getBusinessImpact(clientId: string, dateFrom?: string, dateTo?: string): Promise<ImpactSummary[]> {
  const params = new URLSearchParams()
  if (dateFrom) params.set("date_from", dateFrom)
  if (dateTo) params.set("date_to", dateTo)
  const qs = params.toString()
  return apiFetch<ImpactSummary[]>(`/api/v1/clients/${clientId}/business-impact${qs ? `?${qs}` : ""}`)
}

// ── Benchmarks (Phase 6) ─────────────────────────────────────────────────

export function getClientBenchmarks(
  clientId: string, periodStart?: string, periodEnd?: string,
): Promise<BenchmarkComparison[]> {
  const params = new URLSearchParams()
  if (periodStart) params.set("period_start", periodStart)
  if (periodEnd) params.set("period_end", periodEnd)
  const qs = params.toString()
  return apiFetch<BenchmarkComparison[]>(
    `/api/v1/clients/${clientId}/benchmarks${qs ? `?${qs}` : ""}`,
  )
}

// ── Global dashboard ─────────────────────────────────────────────────────────

function dashboardQuery(f: DashboardFilters, extra?: Record<string, string>): string {
  const p = new URLSearchParams()
  if (f.startDate && f.endDate) {
    p.set("start_date", f.startDate)
    p.set("end_date", f.endDate)
  } else {
    p.set("days", String(f.days ?? 30))
  }
  if (f.clientId) p.set("client_id", f.clientId)
  if (f.category) p.set("category", f.category)
  if (f.eventType) p.set("event_type", f.eventType)
  if (f.attentionOnly) p.set("attention_only", "true")
  for (const [k, v] of Object.entries(extra ?? {})) p.set(k, v)
  return p.toString()
}

export function getDashboardSummary(filters: DashboardFilters): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>(`/api/v1/dashboard/summary?${dashboardQuery(filters)}`)
}

export function getDashboardFeed(
  filters: DashboardFilters,
  offset = 0,
): Promise<DashboardFeedResponse> {
  return apiFetch<DashboardFeedResponse>(
    `/api/v1/dashboard/feed?${dashboardQuery(filters, { offset: String(offset), limit: "50" })}`,
  )
}
