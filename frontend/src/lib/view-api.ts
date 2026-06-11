// frontend/src/lib/view-api.ts
// SERVER-ONLY data fetching for the read-only client view (/view/[token]).
// Sends NO Authorization header — the share token in the path is the
// credential. A 404 (invalid/revoked/archived token) resolves to null so
// pages can call notFound().
import type {
  ClientViewOverview,
  ClientViewScan,
  ClientViewCompetitors,
  ClientViewReport,
  ClientViewAction,
} from "@/types"

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

async function viewFetch<T>(token: string, path: string): Promise<T | null> {
  const res = await fetch(`${BASE}/api/v1/view/${encodeURIComponent(token)}${path}`, {
    cache: "no-store",
  })
  if (res.status === 404) return null
  if (!res.ok) {
    throw new Error(`View API GET ${path} → ${res.status}`)
  }
  return res.json() as Promise<T>
}

export function getViewOverview(token: string): Promise<ClientViewOverview | null> {
  return viewFetch<ClientViewOverview>(token, "/overview")
}

export function getViewScan(token: string): Promise<ClientViewScan | null> {
  return viewFetch<ClientViewScan>(token, "/scan")
}

export function getViewCompetitors(token: string): Promise<ClientViewCompetitors | null> {
  return viewFetch<ClientViewCompetitors>(token, "/competitors")
}

export function getViewReports(token: string): Promise<ClientViewReport[] | null> {
  return viewFetch<ClientViewReport[]>(token, "/reports")
}

export function getViewActions(token: string): Promise<ClientViewAction[] | null> {
  return viewFetch<ClientViewAction[]>(token, "/actions")
}
