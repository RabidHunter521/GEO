// frontend/src/types/index.ts

export interface Client {
  id: string
  name: string
  website: string
  industry: string
  description: string | null
  target_audience: string | null
  city: string | null
  state: string | null
  contact_email: string | null
  brand_authority_score: number
  content_quality_score: number
  technical_foundations_verified: boolean
  structured_data_verified: boolean
  score_drop_threshold: number
  created_at: string
  archived_at: string | null
}

export interface ClientListItem extends Client {
  latest_overall_score: number | null
  last_scan_at: string | null
}

export interface Competitor {
  id: string
  client_id: string
  name: string
  website: string | null
}

export interface GeoScore {
  id: string
  client_id: string
  scan_id: string
  ai_citability: number
  brand_authority: number
  content_quality: number
  technical_foundations: number
  structured_data: number
  overall_score: number
  computed_at: string
}

export interface ScoreBand {
  name: "excellent" | "good" | "fair" | "developing" | "low"
  color: "green" | "yellow" | "red"
}
