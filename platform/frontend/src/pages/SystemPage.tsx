import { useEffect, useState } from "react";

import { getSystemStatus } from "../api/client";
import type { SystemStatus } from "../api/types";


export function SystemPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getSystemStatus().then(setStatus).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "系统状态加载失败");
    });
  }, []);
  return (
    <div>
      <header className="page-heading"><div><p className="eyebrow">安全边界 · 只读</p><h1>系统状态</h1><p>只读展示安全开关，不显示凭据、密钥或提示词。</p></div></header>
      {error ? <div role="alert" className="state-panel">{error}</div> : status ? (
        <dl className="system-grid panel">
          <div><dt>OIDC 身份</dt><dd>{status.oidc_configured ? "已配置" : "待配置"}</dd></div>
          <div><dt>开发身份回退</dt><dd>{status.dev_auth_enabled ? "已开启" : "已关闭"}</dd></div>
          <div><dt>本地开发会话</dt><dd>{status.local_dev_session_enabled ? "仅本机开启" : "已关闭"}</dd></div>
          <div><dt>模型外发</dt><dd>{status.model_egress_enabled ? "已开启" : "默认关闭"}</dd></div>
          <div><dt>获批提供商</dt><dd>{status.approved_model_providers.length || "无"}</dd></div>
          <div><dt>获批用途</dt><dd>{status.approved_model_purposes.length || "无"}</dd></div>
          <div><dt>数据保留</dt><dd>{status.data_retention_days} 天</dd></div>
        </dl>
      ) : <div role="status" className="state-panel">正在读取安全状态…</div>}
    </div>
  );
}
