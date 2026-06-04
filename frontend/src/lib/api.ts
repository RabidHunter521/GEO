// frontend/src/lib/api.ts
// SERVER-ONLY: Do not import this file from client components ("use client").
// Accesses process.env.ADMIN_API_KEY which is a server-side env var.
import type { Client, ClientListItem, Competitor, GeoScore, ToolkitFiles, VerificationResult, CompetitorIntelligenceResponse, ActivityLogEntry } from "@/types"

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
  body: Pick<Client, "name" | "website" | "industry">,
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
      | "contact_email"
      | "brand_authority_score"
      | "content_quality_score"
      | "score_drop_threshold"
    >
  >,
): Promise<Client> {
  return apiFetch<Client>(`/api/v1/clients/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export function getLatestGeoScore(clientId: string): Promise<GeoScore | null> {
  return apiFetch<GeoScore | null>(`/api/v1/clients/${clientId}/geo-score/latest`)
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

export function getActivityLog(clientId: string, limit = 50): Promise<ActivityLogEntry[]> {
  return apiFetch<ActivityLogEntry[]>(
    `/api/v1/clients/${clientId}/activity?limit=${limit}`,
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
