export type DashboardView = "competition" | "enterprise";

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
  view: DashboardView;
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
  model_egress_enabled: boolean;
  approved_model_providers: string[];
  approved_model_purposes: string[];
  data_retention_days: number;
}
