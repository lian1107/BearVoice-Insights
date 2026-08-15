import type {
  DashboardSnapshot,
  DashboardView,
  SourceSummary,
  SystemStatus,
} from "./types";


const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";


function authorizationHeaders(): HeadersInit {
  const token = window.sessionStorage.getItem("bearvoice_access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}


async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: authorizationHeaders(),
  });
  if (!response.ok) {
    throw new Error(
      response.status === 401
        ? "登录已失效，请重新进入系统"
        : `请求失败（${response.status}）`,
    );
  }
  return response.json() as Promise<T>;
}


export function getDashboard(
  product: string,
  view: DashboardView,
): Promise<DashboardSnapshot> {
  const query = new URLSearchParams({ product, view });
  return getJson<DashboardSnapshot>(`/api/dashboard?${query}`);
}


export function getSources(): Promise<SourceSummary[]> {
  return getJson<SourceSummary[]>("/api/sources");
}


export function getSystemStatus(): Promise<SystemStatus> {
  return getJson<SystemStatus>("/api/admin/status");
}
