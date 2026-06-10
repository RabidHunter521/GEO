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

export interface ToolkitFiles {
  id: string
  client_id: string
  llms_txt: string
  schema_json: string
  robots_txt: string
  generated_at: string
  llms_verified: boolean
  schema_verified: boolean
  robots_verified: boolean
  verified_at: string | null
}

export interface VerificationResult {
  llms_verified: boolean
  schema_verified: boolean
  robots_verified: boolean
  technical_foundations_updated: boolean
  structured_data_updated: boolean
}

export interface CompetitorQueryBreakdown {
  category: string
  query_text: string
  brand_detected: boolean
}

export interface CompetitorScore {
  id: string
  name: string
  website: string | null
  ai_citability: number
  queries: CompetitorQueryBreakdown[]
  is_winning: boolean
}

export interface CompetitorIntelligenceResponse {
  client_ai_citability: number | null
  competitors: CompetitorScore[]
  last_scan_at: string | null
}

export interface ActivityLogEntry {
  id: string
  event_type: string
  note: string
  created_at: string
}

export interface Report {
  id: string
  client_id: string
  r2_url: string
  period_start: string
  period_end: string
  overall_score: number
  generated_at: string
  sent_at: string | null
}

export interface ScanQueryResult {
  id: string
  scan_id: string
  competitor_id: string | null
  competitor_name: string | null
  category: string
  query_text: string
  response_text: string | null
  brand_detected: boolean
  hallucination_flagged: boolean
  recommendation_position: number | null
  created_at: string
}

export interface ContentTopic {
  topic: string
  status: "strong" | "weak" | "missing"
}

export interface ContentEntity {
  entity: string
  covered: boolean
}

export interface ContentMetrics {
  word_count: number
  h1_count: number
  faq_count: number
  blog_count: number
  schema_present: boolean
}

export interface ContentAnalysis {
  id: string
  client_id: string
  status: "pending" | "running" | "completed" | "failed"
  topics_json: ContentTopic[]
  entities_json: ContentEntity[]
  entity_coverage_score: number
  content_metrics_json: ContentMetrics
  content_quality_recommendation: string | null
  pages_crawled: number
  analyzed_at: string
}

export interface Scan {
  id: string
  client_id: string
  platform: string
  status: "pending" | "running" | "completed" | "failed"
  triggered_at: string
  completed_at: string | null
  results: ScanQueryResult[]
}
