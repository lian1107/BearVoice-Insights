import { useEffect, useState } from "react";

import {
  AuthenticationRequiredError,
  getAuthOptions,
  getAuthSession,
  startLocalDevSession,
} from "../api/client";
import type { AuthOptions, AuthSession } from "../api/types";
import { EnterpriseRouter, type UiPermission } from "./router";


const UI_PERMISSIONS = new Set<UiPermission>([
  "read_voice",
  "manage_sources",
  "review_taxonomy",
  "review_opportunity",
  "manage_evaluation",
  "admin",
]);


function toUiPermissions(session: AuthSession): UiPermission[] {
  return session.permissions.filter(
    (permission): permission is UiPermission => UI_PERMISSIONS.has(permission as UiPermission),
  );
}


function LoginPage({
  options,
  error,
  pending,
  onLocalLogin,
}: {
  options: AuthOptions;
  error: string | null;
  pending: boolean;
  onLocalLogin: () => void;
}) {
  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="auth-title">
        <span className="brand__mark" aria-hidden="true">B</span>
        <p className="eyebrow">BearVoice · 私有化环境</p>
        <h1 id="auth-title">本地开发登录</h1>
        <p>开发会话仅限本机、短期有效，并保存在 HttpOnly Cookie 中；生产环境不会开放此入口。</p>
        {options.local_dev_session ? (
          <button className="button button--primary" disabled={pending} onClick={onLocalLogin} type="button">
            {pending ? "正在建立安全会话…" : "进入本地开发环境"}
          </button>
        ) : options.oidc_configured ? (
          <p className="auth-note">请通过企业 SSO 进入系统。</p>
        ) : (
          <p className="auth-note">当前环境尚未配置可用的登录方式。</p>
        )}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
      </section>
    </main>
  );
}


export function App() {
  const [session, setSession] = useState<AuthSession | null>();
  const [options, setOptions] = useState<AuthOptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let active = true;
    getAuthSession()
      .then((current) => active && setSession(current))
      .catch(async (cause: unknown) => {
        if (!active) return;
        if (!(cause instanceof AuthenticationRequiredError)) {
          setError(cause instanceof Error ? cause.message : "登录状态检查失败");
        }
        try {
          const available = await getAuthOptions();
          if (active) {
            setOptions(available);
            setSession(null);
          }
        } catch (optionError: unknown) {
          if (active) {
            setError(optionError instanceof Error ? optionError.message : "登录方式读取失败");
            setOptions({ local_dev_session: false, oidc_configured: false });
            setSession(null);
          }
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function localLogin() {
    setPending(true);
    setError(null);
    try {
      await startLocalDevSession();
      setSession(await getAuthSession());
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "本地开发登录失败");
    } finally {
      setPending(false);
    }
  }

  if (session === undefined) {
    return <main className="auth-shell"><div className="state-panel" role="status">正在检查登录状态…</div></main>;
  }
  if (session === null) {
    return (
      <LoginPage
        error={error}
        onLocalLogin={localLogin}
        options={options ?? { local_dev_session: false, oidc_configured: false }}
        pending={pending}
      />
    );
  }
  return <EnterpriseRouter permissions={toUiPermissions(session)} />;
}
