import type {
  ActionCreateCommand,
  ActionItem,
  ActionTransitionCommand,
  AuthOptions,
  AuthSession,
  CsvQualityPreview,
  GoldenReviewCommand,
  GoldenReviewItem,
  DashboardSnapshot,
  EvidenceDetail,
  OpportunityDetail,
  OpportunityReviewCommand,
  OpportunityReviewResult,
  OpportunitySummary,
  ProductDecisionInsight,
  ModelProviderOption,
  ModelAnalysisJobStatus,
  OutcomeCreateCommand,
  OutcomeMeasurement,
  SourceSummary,
  SystemStatus,
  TaxonomyRevisionCommand,
  TaxonomySummary,
  UploadAnalysisResult,
  UploadSourceCommand,
} from "./types";


const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";


export class AuthenticationRequiredError extends Error {
  constructor() {
    super("需要登录后才能读取企业数据");
    this.name = "AuthenticationRequiredError";
  }
}


async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "same-origin",
  });
  if (!response.ok) {
    if (response.status === 401) {
      throw new AuthenticationRequiredError();
    }
    throw new Error(`请求失败（${response.status}）`);
  }
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new Error("服务路由异常：接口没有返回 JSON 数据");
  }
  return response.json() as Promise<T>;
}


async function sendJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    credentials: "same-origin",
  });
  if (!response.ok) {
    if (response.status === 401) {
      throw new AuthenticationRequiredError();
    }
    const detail = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `提交失败（${response.status}）`);
  }
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new Error("服务路由异常：接口没有返回 JSON 数据");
  }
  return response.json() as Promise<T>;
}


export function getAuthOptions(): Promise<AuthOptions> {
  return getJson<AuthOptions>("/api/auth/options");
}


export function getAuthSession(): Promise<AuthSession> {
  return getJson<AuthSession>("/api/auth/session");
}


export function startLocalDevSession(): Promise<{ mode: string; expires_at: string }> {
  return sendJson<{ mode: string; expires_at: string }>("/api/auth/dev-session", {});
}


export function getDashboard(
  product: string,
): Promise<DashboardSnapshot> {
  const query = new URLSearchParams({ product });
  return getJson<DashboardSnapshot>(`/api/dashboard?${query}`);
}


export function getProductDecisionInsight(
  product: string,
): Promise<ProductDecisionInsight> {
  const query = new URLSearchParams({ product });
  return getJson<ProductDecisionInsight>(`/api/insights/decision?${query}`);
}


export function getSources(): Promise<SourceSummary[]> {
  return getJson<SourceSummary[]>("/api/sources");
}


export function getAnalysisProviders(): Promise<ModelProviderOption[]> {
  return getJson<ModelProviderOption[]>("/api/analysis/providers");
}


export function getAnalysisJob(jobId: string): Promise<ModelAnalysisJobStatus> {
  return getJson<ModelAnalysisJobStatus>(`/api/analysis/jobs/${jobId}`);
}


export async function previewVoiceCsv(file: File): Promise<CsvQualityPreview> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/sources/preview`, {
    method: "POST",
    body,
    credentials: "same-origin",
  });
  if (!response.ok) {
    if (response.status === 401) {
      throw new AuthenticationRequiredError();
    }
    const problem = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(problem?.detail ?? `预检失败（${response.status}）`);
  }
  return response.json() as Promise<CsvQualityPreview>;
}


export async function uploadVoiceCsv(
  file: File,
  command: UploadSourceCommand,
): Promise<UploadAnalysisResult> {
  const body = new FormData();
  body.append("file", file);
  body.append("source_name", command.sourceName);
  body.append("channel", command.channel);
  body.append("product", command.product);
  body.append("product_column", command.productColumn);
  body.append("column_mapping", JSON.stringify(command.columnMapping));
  body.append("analysis_provider", command.analysisProvider);
  const response = await fetch(`${API_BASE_URL}/api/sources/upload`, {
    method: "POST",
    body,
    credentials: "same-origin",
  });
  if (!response.ok) {
    if (response.status === 401) {
      throw new AuthenticationRequiredError();
    }
    const problem = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(problem?.detail ?? `上传失败（${response.status}）`);
  }
  return response.json() as Promise<UploadAnalysisResult>;
}


export function getSystemStatus(): Promise<SystemStatus> {
  return getJson<SystemStatus>("/api/admin/status");
}


export function getOpportunities(product = "养生壶"): Promise<OpportunitySummary[]> {
  const query = new URLSearchParams({ product });
  return getJson<OpportunitySummary[]>(`/api/opportunities?${query}`);
}


export function getOpportunity(id: string): Promise<OpportunityDetail> {
  return getJson<OpportunityDetail>(`/api/opportunities/${id}`);
}


export function getEvidence(id: string, opportunityId?: string): Promise<EvidenceDetail> {
  const query = opportunityId
    ? `?${new URLSearchParams({ opportunity_id: opportunityId })}`
    : "";
  return getJson<EvidenceDetail>(`/api/evidence/${id}${query}`);
}


export function reviewOpportunity(
  id: string,
  command: OpportunityReviewCommand,
): Promise<OpportunityReviewResult> {
  return sendJson<OpportunityReviewResult>(`/api/opportunities/${id}/reviews`, command);
}


export function createOpportunityAction(
  opportunityId: string,
  command: ActionCreateCommand,
): Promise<ActionItem> {
  return sendJson<ActionItem>(`/api/opportunities/${opportunityId}/actions`, command);
}


export function transitionOpportunityAction(
  opportunityId: string,
  actionId: string,
  command: ActionTransitionCommand,
): Promise<ActionItem> {
  return sendJson<ActionItem>(
    `/api/opportunities/${opportunityId}/actions/${actionId}/transitions`,
    command,
  );
}


export function createActionOutcome(
  opportunityId: string,
  actionId: string,
  command: OutcomeCreateCommand,
): Promise<OutcomeMeasurement> {
  return sendJson<OutcomeMeasurement>(
    `/api/opportunities/${opportunityId}/actions/${actionId}/outcomes`,
    command,
  );
}


export function getTaxonomies(product = "养生壶"): Promise<TaxonomySummary[]> {
  const query = new URLSearchParams({ product });
  return getJson<TaxonomySummary[]>(`/api/taxonomies?${query}`);
}


export function createTaxonomyRevision(
  taxonomyId: string,
  command: TaxonomyRevisionCommand,
): Promise<TaxonomySummary> {
  return sendJson<TaxonomySummary>(`/api/taxonomies/${taxonomyId}/revisions`, command);
}


export function getGoldenReviewQueue(): Promise<GoldenReviewItem[]> {
  return getJson<GoldenReviewItem[]>("/api/evaluations/golden-examples");
}


export function submitGoldenReview(
  exampleId: string,
  command: GoldenReviewCommand,
): Promise<GoldenReviewItem> {
  return sendJson<GoldenReviewItem>(`/api/evaluations/golden-examples/${exampleId}/reviews`, command);
}
