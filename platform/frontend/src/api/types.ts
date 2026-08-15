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
  actions?: ActionItem[];
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

export interface DecisionDimensionSlice {
  value: string;
  count: number;
  percentage: number;
  denominator: number;
}

export type DecisionDimensionKey =
  | "channel"
  | "sku"
  | "batch"
  | "version"
  | "lifecycle_stage"
  | "risk_level";

export interface DecisionInsightCoverage {
  total_voices: number;
  total_signals: number;
  period_start: string | null;
  period_end: string | null;
  days: number;
  trend_allowed: boolean;
  channels: string[];
  has_business_denominator: false;
  denominator_notice: string;
  limitations: string[];
}

export interface DecisionPattern {
  pattern_id: string;
  signal_type: string;
  object_name: string | null;
  issue: string;
  risk_level: string;
  voice_count: number;
  share: number;
  denominator: number;
  channels: string[];
  skus: string[];
  batches: string[];
  versions: string[];
  lifecycle_stages: string[];
  scenarios: string[];
  latent_needs: string[];
  root_cause_hypotheses: string[];
  improvement_directions: string[];
  validation_suggestions: string[];
  missing_information: string[];
  supporting_evidence_ids: string[];
  conflict_notice: string | null;
}

export interface ProductDecisionCard {
  card_id: string;
  problem: string;
  why_now: string;
  evidence_level: "directional" | "local_descriptive";
  risk_level: string;
  voice_count: number;
  share: number;
  recommended_direction: string;
  validation_plan: string;
  human_owner: string;
  human_review_required: true;
  forbidden_claims: string[];
  priority_explanation: string;
  supporting_evidence_ids: string[];
}

export interface DecisionInsightGovernance {
  scope_notice: string;
  causality_notice: string;
  financial_notice: string;
  human_review_notice: string;
}

export interface ProductDecisionInsight {
  product: string;
  analysis_run_id: string;
  coverage: DecisionInsightCoverage;
  dimensions: Record<DecisionDimensionKey, DecisionDimensionSlice[]>;
  patterns: DecisionPattern[];
  decision_cards: ProductDecisionCard[];
  governance: DecisionInsightGovernance;
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

export interface UploadAnalysisResult {
  batch_id: string;
  job_id: string | null;
  analysis_run_id: string | null;
  raw_count: number;
  deduplicated_count: number;
  quarantined_count: number;
  signal_count: number;
  cluster_count: number;
  opportunity_count: number;
  status: "pending_review" | string;
  reused: boolean;
  analysis_mode: "offline_keyword_rules" | "governed_ai_semantic";
  analysis_provider: AnalysisProvider;
  model_calls: number;
  requested_items?: number;
  processed_items?: number;
  attempt_count?: number;
  reserved_cost_amount?: number;
  notice: string;
}

export interface ModelAnalysisJobStatus {
  job_id: string;
  analysis_run_id: string | null;
  batch_id: string;
  status: "queued" | "dispatched" | "running" | "succeeded" | "failed" | "dispatch_failed";
  product: string;
  analysis_provider: Exclude<AnalysisProvider, "local">;
  requested_items: number;
  processed_items: number;
  model_calls: number;
  signal_count: number;
  cluster_count: number;
  opportunity_count: number;
  attempt_count: number;
  reserved_cost_amount: number;
  input_tokens: number;
  output_tokens: number;
  error_code: string | null;
  error_message: string | null;
  notice: string;
}

export interface UploadSourceCommand {
  sourceName: string;
  channel: string;
  product: string;
  productColumn: string;
  columnMapping: Record<string, string>;
  analysisProvider: AnalysisProvider;
}

export type AnalysisProvider = "local" | "deepseek" | "glm" | "minimax" | "qwen" | "custom";

export interface ModelProviderOption {
  provider: AnalysisProvider;
  configured: boolean;
  approved: boolean;
  model: string | null;
}

export interface CsvMappingSuggestion {
  field: string;
  label: string;
  required: boolean;
  suggested_column: string | null;
  confidence: number;
  method: "deterministic_alias_rules";
  reason: string;
}

export interface CsvColumnProfile {
  column: string;
  null_rate: number;
  unique_rate: number;
}

export interface CsvQualityPreview {
  encoding: "utf-8" | "utf-8-sig";
  row_count: number;
  columns: string[];
  required_fields_matched: boolean;
  missing_required_fields: string[];
  mapping_suggestions: CsvMappingSuggestion[];
  column_mapping: Record<string, string>;
  column_profiles: CsvColumnProfile[];
  date_parse_rate: number | null;
  duplicate_id_count: number;
  exact_duplicate_count: number;
  near_duplicate_or_template_count: number;
  quality_hints: string[];
  quarantined_count: number;
  quarantine_reasons: Array<{ reason: string; count: number }>;
  suggestion_method: "deterministic_alias_rules";
  ai_used: false;
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
  collaborating_departments?: string[];
  objective?: string;
  due_date?: string;
  external_reference?: string;
}

export interface OpportunityReviewResult {
  status: string;
  audit: AuditEntry;
  actions?: ActionItem[];
}

export type ActionItemStatus =
  | "planned"
  | "in_progress"
  | "blocked"
  | "completed"
  | "cancelled";

export interface OutcomeMeasurement {
  id: string;
  metric_name: string;
  metric_definition: string;
  unit: string;
  baseline_value: number | null;
  target_value: number | null;
  actual_value: number | null;
  observation_window: string;
  measured_at: string | null;
  conclusion: string;
  limitations: string;
  recorded_by: string;
  causality_notice: string;
}

export interface ActionItem {
  id: string;
  owner: string;
  collaborating_departments: string[];
  objective: string;
  due_at: string | null;
  status: ActionItemStatus;
  external_reference: string | null;
  decision_rationale: string;
  outcomes: OutcomeMeasurement[];
  audit_timeline?: AuditEntry[];
}

export interface ActionCreateCommand {
  owner: string;
  collaborating_departments: string[];
  objective: string;
  due_date?: string;
  external_reference?: string;
  decision_rationale: string;
}

export interface ActionTransitionCommand {
  target_status: ActionItemStatus;
  reason: string;
}

export interface OutcomeCreateCommand {
  metric_name: string;
  metric_definition: string;
  unit: string;
  baseline_value?: number;
  target_value?: number;
  actual_value?: number;
  observation_window: string;
  conclusion: string;
  limitations: string;
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
