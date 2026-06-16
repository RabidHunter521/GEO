// frontend/src/lib/api.ts
// SERVER-ONLY: Do not import this file from client components ("use client").
// Accesses process.env.ADMIN_API_KEY which is a server-side env var.
import type { Client, ClientListItem, Competitor, GeoScore, ToolkitFiles, VerificationResult, CompetitorIntelligenceResponse, ActivityLogEntry, Report, Scan, ContentAnalysis, ContentRoadmap, ActionRecommendation, AiTrafficSnapshot, ShareTokenResponse, WinLossResponse, ContentBrief, CompetitorTrendsResponse, IndustryBenchmark, ScanDiffResponse } from "@/types"

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

function apiHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${process.env.ADMIN_API_KEY}`,
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...apiHeaders(), ...init?.headers },
    cache: "no-store",
  })
  if (res.status === 204) return undefined as T
  if (!res.ok) {
    throw new Error(`API ${init?.method ?? "GET"} ${path} → ${res.status}`)
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
    Partial<Pick<Client, "is_prospect">>,
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
      | "contact_email"
      | "brand_authority_score"
      | "brand_authority_evidence"
      | "content_quality_score"
      | "content_quality_evidence"
      | "score_drop_threshold"
      | "scan_cadence_days"
      | "enabled_platforms"
      | "is_prospect"
      | "internal_notes"
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

export function getLatestGeoScore(clientId: string): Promise<GeoScore | null> {
  return apiFetch<GeoScore | null>(`/api/v1/clients/${clientId}/geo-score/latest`)
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

export function getIndustryBenchmark(clientId: string): Promise<IndustryBenchmark | null> {
  return apiFetch<IndustryBenchmark | null>(`/api/v1/clients/${clientId}/benchmark`)
}

export function getActivityLog(clientId: string, limit = 50, skip = 0): Promise<ActivityLogEntry[]> {
  return apiFetch<ActivityLogEntry[]>(
    `/api/v1/clients/${clientId}/activity?limit=${limit}&skip=${skip}`,
  )
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
