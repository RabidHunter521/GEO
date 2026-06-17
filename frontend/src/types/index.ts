// frontend/src/types/index.ts

export type Platform = "chatgpt" | "perplexity" | "gemini" | "claude"

export const SCAN_PLATFORMS: Platform[] = ["chatgpt", "perplexity", "gemini", "claude"]

export const PLATFORM_LABELS: Record<Platform, string> = {
  chatgpt: "ChatGPT",
  perplexity: "Perplexity",
  gemini: "Gemini",
  claude: "Claude",
}

export interface PlatformBreakdownEntry {
  visibility: number
  queries: number
  detected: number
  status: "ok" | "unavailable"
}

export type PlatformBreakdown = Partial<Record<Platform, PlatformBreakdownEntry>>

export interface Client {
  id: string
  name: string
  website: string
  industry: string
  description: string | null
  target_audience: string | null
  city: string | null
  state: string | null
  country: string | null
  contact_email: string | null
  logo_url: string | null
  brand_authority_score: number
  brand_authority_evidence: string | null
  content_quality_score: number
  content_quality_evidence: string | null
  technical_foundations_verified: boolean
  structured_data_verified: boolean
  score_drop_threshold: number
  scan_cadence_days: number
  enabled_platforms: Platform[]
  share_token: string | null
  share_token_created_at: string | null
  created_at: string
  archived_at: string | null
  is_prospect: boolean
  internal_notes: string | null
}

export interface ShareTokenResponse {
  share_token: string
  share_token_created_at: string
}

export interface ClientListItem extends Client {
  latest_overall_score: number | null
  last_scan_at: string | null
  previous_overall_score: number | null
  latest_scan_status: "pending" | "running" | "completed" | "failed" | null
  latest_scan_triggered_at: string | null
  next_scan_due: string | null
  is_scan_overdue: boolean
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
  platform_breakdown: PlatformBreakdown | null
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
  platform: Platform
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
  platform_visibility: Partial<Record<Platform, number>>
  winning_platforms: Platform[]
}

export interface CompetitorIntelligenceResponse {
  client_ai_citability: number | null
  client_platform_visibility: Partial<Record<Platform, number>>
  competitors: CompetitorScore[]
  last_scan_at: string | null
}

// ── Win/loss analysis (admin only) ───────────────────────────────────────────

export type WinLossOutcome = "won" | "lost" | "shared" | "open"

export interface ContentBrief {
  id: string
  title: string
  angle: string
  outline: string[]
  competitors_seen: string[]
  generated_at: string
}

export interface WinLossEntry {
  result_id: string
  platform: Platform
  category: string
  query_text: string
  client_seen: boolean
  competitors_seen: string[]
  outcome: WinLossOutcome
  brief: ContentBrief | null
}

export interface WinLossResponse {
  scan_id: string | null
  last_scan_at: string | null
  summary: Partial<Record<WinLossOutcome, number>>
  entries: WinLossEntry[]
}

// ── Visibility trends ─────────────────────────────────────────────────────────

export interface TrendScanPoint {
  scan_id: string
  completed_at: string
}

export interface TrendSeries {
  competitor_id: string | null // null = the client
  name: string
  points: (number | null)[]
}

export interface CompetitorTrendsResponse {
  scans: TrendScanPoint[]
  client: TrendSeries
  competitors: TrendSeries[]
}

// ── Industry benchmark ────────────────────────────────────────────────────────

export interface IndustryBenchmark {
  industry: string
  peer_count: number
  client_score: number
  industry_average: number
  rank: number
  top_percent: number
}

// ── Scan diff ("Since last scan") ────────────────────────────────────────────

export interface ScanDiffQuery {
  platform: string
  category: string
  query_text: string
}

export interface ScanDiffResponse {
  latest_scan_id: string | null
  previous_scan_id: string | null
  latest_scan_at: string | null
  previous_scan_at: string | null
  latest_visibility: number | null
  previous_visibility: number | null
  newly_seen: ScanDiffQuery[]
  newly_unseen: ScanDiffQuery[]
  has_comparison: boolean
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
  platform: Platform
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

export interface SuggestedContentItem {
  topic: string
  title: string
  rationale: string
}

export interface ContentAnalysis {
  id: string
  client_id: string
  status: "pending" | "running" | "completed" | "failed"
  topics_json: ContentTopic[]
  entities_json: ContentEntity[]
  suggested_content_json: SuggestedContentItem[]
  entity_coverage_score: number
  content_metrics_json: ContentMetrics
  content_quality_recommendation: string | null
  pages_crawled: number
  analyzed_at: string
}

export interface RoadmapItem {
  week: number // 1–12
  theme: string
  priority: "high" | "medium" | "low"
  target_queries: string[]
  competitors_winning: string[]
  content_type: string
  suggested_title: string
  rationale: string
  article_content: string | null
}

export interface ContentRoadmap {
  id: string
  client_id: string
  status: "pending" | "running" | "completed" | "failed"
  roadmap_json: RoadmapItem[]
  source_query_count: number
  generated_at: string
}

export interface ActionRecommendation {
  id: string
  client_id: string
  action_text: string
  dimension: "ai_citability" | "brand_authority" | "content_quality" | "technical_foundations" | "structured_data"
  estimated_impact: number
  priority: "high" | "medium" | "low"
  status: "open" | "done" | "dismissed" | "superseded"
  generated_at: string
}

export interface AiTrafficSnapshot {
  id: string
  client_id: string
  period: string
  ai_visitors: number
  created_at: string
  updated_at: string
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

// ── Read-only client view (/view/[token]) ────────────────────────────────────
// Wire names are client-safe by design: seen_by_ai, ai_search_ranking,
// visibility_frequency. Never extend these with internal fields.

export interface ClientViewProfile {
  name: string
  website: string
  industry: string
  logo_url: string | null
  is_prospect: boolean
}

export interface ClientViewScore {
  overall_score: number
  ai_visibility: number
  brand_authority: number
  content_quality: number
  technical_foundations: number
  structured_data: number
  computed_at: string
}

export interface ClientViewScorePoint {
  overall_score: number
  computed_at: string
}

export interface ClientViewTrafficPoint {
  period: string
  ai_visitors: number
}

export interface ClientViewPlatform {
  platform_label: string
  seen_by_ai: boolean
  visibility_frequency: number | null // null = platform unavailable during latest scan
}

export interface ClientViewBenchmark {
  industry: string
  peer_count: number
  industry_average: number
  top_percent: number
}

export interface ClientViewOverview {
  profile: ClientViewProfile
  latest_score: ClientViewScore | null
  platforms: ClientViewPlatform[]
  benchmark: ClientViewBenchmark | null
  score_history: ClientViewScorePoint[]
  traffic: ClientViewTrafficPoint[]
  change_narrative: string | null
  change_narrative_period: string | null
  has_our_work: boolean
  has_content_plan: boolean
}

export interface ClientViewScanResult {
  platform_label: string
  category: string
  query_text: string
  seen_by_ai: boolean
  ai_search_ranking: number | null
}

export interface ClientViewScan {
  completed_at: string | null
  results: ClientViewScanResult[]
}

export interface ClientViewCompetitorQuery {
  platform_label: string
  category: string
  query_text: string
  seen_by_ai: boolean
}

export interface ClientViewCompetitor {
  name: string
  website: string | null
  visibility_frequency: number
  is_winning: boolean
  platform_visibility: Record<string, number>
  winning_platform_labels: string[]
  queries: ClientViewCompetitorQuery[]
}

export interface ClientViewCompetitors {
  your_visibility_frequency: number | null
  your_platform_visibility: Record<string, number>
  competitors: ClientViewCompetitor[]
  last_scan_at: string | null
}

export interface ClientViewTrendSeries {
  name: string
  is_you: boolean
  points: (number | null)[]
}

export interface ClientViewCompetitorTrends {
  checked_at: string[]
  series: ClientViewTrendSeries[]
}

export interface ClientViewReport {
  id: string
  period_start: string
  period_end: string
  overall_score: number
  generated_at: string
  download_url: string
}

export interface ClientViewAction {
  action_text: string
  dimension: "ai_citability" | "brand_authority" | "content_quality" | "technical_foundations" | "structured_data"
  priority: "high" | "medium" | "low"
  generated_at: string
}

export interface ClientViewIssueGroup {
  dimension: "ai_visibility" | "brand_authority" | "content_quality" | "technical_foundations" | "structured_data"
  dimension_label: string
  issues: string[]
}

// --- Deliverables surfaced read-only on the client view ---

export interface ClientViewToolkit {
  llms_txt: string
  schema_json: string
  robots_txt: string
  llms_verified: boolean
  schema_verified: boolean
  robots_verified: boolean
  verified_at: string | null
  generated_at: string
}

export interface ClientViewRoadmapItem {
  week: number
  theme: string
  priority: "high" | "medium" | "low"
  content_type: string
  suggested_title: string
  rationale: string
  target_queries: string[]
  competitors_winning: string[]
  article_content: string | null
}

export interface ClientViewRoadmap {
  items: ClientViewRoadmapItem[]
  source_query_count: number
  generated_at: string
}

export interface ClientViewTopic {
  topic: string
  status: "strong" | "weak" | "missing"
}

export interface ClientViewEntity {
  entity: string
  covered: boolean
}

export interface ClientViewSuggestedContent {
  topic: string
  title: string
  rationale: string
}

export interface ClientViewContentGaps {
  topics: ClientViewTopic[]
  entities: ClientViewEntity[]
  suggested_content: ClientViewSuggestedContent[]
  quality_recommendation: string | null
  analyzed_at: string
}

export interface ClientViewActivity {
  kind: string
  label: string
  note: string
  created_at: string
}

// ── Competitor Gap Matrix (/clients/gap-matrix) ───────────────────────────────

export interface GapCell {
  category: string
  client_visibility: number | null
  top_competitor_visibility: number | null
  top_competitor_name: string | null
  competitors_winning: boolean
}

export interface GapMatrixRow {
  client_id: string
  client_name: string
  cells: GapCell[]
}

export interface GapMatrixResponse {
  categories: string[]
  rows: GapMatrixRow[]
}
