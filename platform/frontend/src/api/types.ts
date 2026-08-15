export interface AuthOptions {
  local_dev_session: boolean;
  oidc_configured: boolean;
}

export interface AuthSession {
  subject: string;
  roles: string[];
  permissions: string[];
  product_lines: string[];
}

export interface SignalMetric {
  signal_type: string;
  count: number;
  percentage: number;
  denominator: number;
}

export interface ClusterMetric {
  id: string;
  name: string;
  signal_type: string | null;
  count: number;
  percentage: number;
  denominator: number;
}

export interface OpportunitySummary {
  id: string;
  title: string;
  opportunity_type: string;
  status: string;
  safety_level: string | null;
  priority_override: string | null;
  severity: string | null;
  impact_scope: string | null;
  evidence_count: number;
}

export interface CoverageBoundary {
  channel: string;
  period_start: string | null;
  period_end: string | null;
  days: number;
  trend_allowed: boolean;
  limitation: string;
}

export interface DashboardSnapshot {
  product: string;
  analysis_run_id: string;
  total_voices: number;
  actionable_voices: number;
  denominator: number;
  signals: SignalMetric[];
  top_clusters: ClusterMetric[];
  opportunities: OpportunitySummary[];
  coverage: CoverageBoundary;
}

export interface SourceSummary {
  id: string;
  name: string;
  channel: string;
  connection_status: string;
  raw_count: number;
  deduplicated_count: number;
  quarantined_count: number;
}

export interface SystemStatus {
  oidc_configured: boolean;
  dev_auth_enabled: boolean;
  local_dev_session_enabled: boolean;
  model_egress_enabled: boolean;
  approved_model_providers: string[];
  approved_model_purposes: string[];
  data_retention_days: number;
}

export interface EvidenceDetail {
  id: string;
  quote: string;
  voice_record_id: string;
  source: string;
  product: string;
  channel: string;
  occurred_at: string | null;
  analysis_run_id: string;
  signal_type: string;
  object_name: string | null;
  privacy_status: string;
  direction: "support" | "oppose";
}

export interface AuditEntry {
  id: string;
  action: string;
  actor_id: string;
  reason: string;
  created_at: string;
}

export interface OpportunityDetail extends OpportunitySummary {
  problem: string;
  evidence_ids: string[];
  audit_timeline: AuditEntry[];
}

export interface OpportunityReviewCommand {
  decision: "approve" | "request_changes" | "reject";
  reason: string;
  owner?: string;
  due_date?: string;
  external_reference?: string;
}

export interface OpportunityReviewResult {
  status: string;
  audit: AuditEntry;
}

export interface TaxonomySummary {
  id: string;
  status: string;
  origin: string;
  parent_version_id: string | null;
  cluster_count: number;
}

export interface TaxonomyRevisionCommand {
  operation: "rename" | "merge" | "split" | "remove" | "restore";
  cluster_ids: string[];
  new_name: string;
  reason: string;
  split_groups?: Array<{ name: string; signal_ids: string[] }>;
}

export interface GoldenReviewItem {
  id: string;
  redacted_input: string;
  model_suggestion: string;
  reviewer_one: string | null;
  reviewer_two: string | null;
  adjudication: string | null;
  review_status: string;
  difficulty_tags: string[];
}

export interface GoldenReviewCommand {
  signal: string;
  object_name: string;
  evidence_text: string;
}
