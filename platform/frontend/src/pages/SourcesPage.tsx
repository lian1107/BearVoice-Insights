import { useEffect, useState, type FormEvent } from "react";
import { AlertTriangle, CheckCircle2, FileSpreadsheet, ShieldCheck, Sparkles, Upload } from "lucide-react";

import { getAnalysisJob, getAnalysisProviders, getSources, previewVoiceCsv, uploadVoiceCsv } from "../api/client";
import type { AnalysisProvider, CsvQualityPreview, ModelAnalysisJobStatus, ModelProviderOption, SourceSummary, UploadAnalysisResult, UploadSourceCommand } from "../api/types";


const LOCAL_PROVIDER: ModelProviderOption = {
  provider: "local",
  configured: true,
  approved: true,
  model: "local-rule-baseline-v1",
};

const PROVIDER_LABELS: Record<AnalysisProvider, string> = {
  local: "本地规则基线（0 次模型调用）",
  deepseek: "DeepSeek",
  glm: "智谱 GLM",
  minimax: "MiniMax",
  qwen: "通义千问",
  custom: "自定义兼容模型",
};


export function SourcesPage({
  uploadCsv = uploadVoiceCsv,
  previewCsv = previewVoiceCsv,
  loadSources = getSources,
  loadProviders = getAnalysisProviders,
  loadJob = getAnalysisJob,
}: {
  uploadCsv?: (file: File, command: UploadSourceCommand) => Promise<UploadAnalysisResult>;
  previewCsv?: (file: File) => Promise<CsvQualityPreview>;
  loadSources?: () => Promise<SourceSummary[]>;
  loadProviders?: () => Promise<ModelProviderOption[]>;
  loadJob?: (jobId: string) => Promise<ModelAnalysisJobStatus>;
}) {
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [prechecking, setPrechecking] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [sourceName, setSourceName] = useState("路演文件上传");
  const [channel, setChannel] = useState("天猫");
  const [product, setProduct] = useState("养生壶");
  const [preview, setPreview] = useState<CsvQualityPreview | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [providers, setProviders] = useState<ModelProviderOption[]>([LOCAL_PROVIDER]);
  const [analysisProvider, setAnalysisProvider] = useState<AnalysisProvider>("local");
  const [result, setResult] = useState<UploadAnalysisResult | null>(null);
  const refreshSources = () => loadSources().then(setSources);
  useEffect(() => {
    refreshSources()
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "来源加载失败");
      })
      .finally(() => setLoading(false));
    // Source loader is stable in production; test overrides are intentionally one-shot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    loadProviders()
      .then((items) => setProviders(items.length ? items : [LOCAL_PROVIDER]))
      .catch(() => setProviders([LOCAL_PROVIDER]));
  }, [loadProviders]);
  useEffect(() => {
    if (!result?.job_id || ["succeeded", "failed", "dispatch_failed"].includes(result.status)) return;
    let cancelled = false;
    const refreshJob = async () => {
      try {
        const job = await loadJob(result.job_id as string);
        if (cancelled) return;
        setResult((current) => current ? {
          ...current,
          analysis_run_id: job.analysis_run_id,
          status: job.status,
          signal_count: job.signal_count,
          cluster_count: job.cluster_count,
          opportunity_count: job.opportunity_count,
          model_calls: job.model_calls,
          requested_items: job.requested_items,
          processed_items: job.processed_items,
          attempt_count: job.attempt_count,
          reserved_cost_amount: job.reserved_cost_amount,
          notice: job.notice,
        } : current);
      } catch (reason: unknown) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "后台任务状态读取失败");
      }
    };
    void refreshJob();
    const timer = window.setInterval(() => void refreshJob(), 2_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [loadJob, result?.job_id, result?.status]);

  function chooseFile(selected: File | null) {
    setFile(selected);
    setPreview(null);
    setColumnMapping({});
    setResult(null);
    setError(null);
  }

  async function runPreview() {
    if (!file) {
      setError("请先选择 CSV 文件");
      return;
    }
    setPrechecking(true);
    setError(null);
    setResult(null);
    try {
      const inspected = await previewCsv(file);
      setPreview(inspected);
      setColumnMapping(inspected.column_mapping);
    } catch (reason: unknown) {
      setPreview(null);
      setColumnMapping({});
      setError(reason instanceof Error ? reason.message : "数据预检失败");
    } finally {
      setPrechecking(false);
    }
  }

  const requiredFields = preview?.mapping_suggestions
    .filter((item) => item.required)
    .map((item) => item.field) ?? [];
  const mappingReady = Boolean(preview)
    && requiredFields.every((field) => Boolean(columnMapping[field]));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("请先选择 CSV 文件");
      return;
    }
    if (!preview || !mappingReady) {
      setError("请先完成数据预检，并确认原声 ID、原声内容和商品标题映射");
      return;
    }
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const uploaded = await uploadCsv(file, {
        sourceName: sourceName.trim(),
        channel: channel.trim(),
        product: product.trim(),
        productColumn: columnMapping.product,
        columnMapping,
        analysisProvider,
      });
      setResult(uploaded);
      await refreshSources();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "上传分析失败");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <header className="page-heading">
        <div><p className="eyebrow">上传一次 · 全程可追溯</p><h1>数据接入与分析</h1><p>把原声 CSV 交给后端，完成校验、去重、脱敏、主题聚合与机会草稿。</p></div>
      </header>

      <section className="upload-workspace" aria-labelledby="upload-title">
        <form className="panel upload-card" onSubmit={submit}>
          <div className="upload-card__heading">
            <span className="upload-card__icon"><Upload aria-hidden="true" size={21} /></span>
            <div><p className="eyebrow">私有化默认 · 国内模型可选</p><h2 id="upload-title">上传 CSV 并生成可审核洞察</h2></div>
          </div>
          <label className="file-drop">
            <FileSpreadsheet aria-hidden="true" size={28} />
            <strong>{file?.name ?? "选择客户原声 CSV"}</strong>
            <span>UTF-8 编码，最大 10 MB；先预检数据质量，再确认字段映射</span>
            <input accept=".csv,text/csv" aria-label="客户原声 CSV" onChange={(event) => chooseFile(event.target.files?.[0] ?? null)} type="file" />
          </label>
          {preview ? (
            <div className="quality-preview" aria-label="数据质量预检结果">
              <div className="quality-summary">
                <div><strong>{preview.row_count}</strong><span>数据行</span></div>
                <div><strong>{preview.encoding.toUpperCase()}</strong><span>编码</span></div>
                <div><strong>{preview.quarantined_count}</strong><span>建议隔离</span></div>
                <div><strong>{Math.max(preview.duplicate_id_count, preview.exact_duplicate_count) + preview.near_duplicate_or_template_count}</strong><span>疑似重复</span></div>
              </div>
              <div className="mapping-heading">
                <div><strong>确认字段映射</strong><span>必填项需全部确认后才能导入</span></div>
                <span className="rule-badge">确定性别名规则 · 未调用 AI</span>
              </div>
              <div className="mapping-grid">
                {preview.mapping_suggestions.map((suggestion) => (
                  <label className="field" key={suggestion.field}>
                    {suggestion.label}{suggestion.required ? " *" : ""}
                    <select
                      aria-label={`${suggestion.label}映射`}
                      onChange={(event) => setColumnMapping((current) => {
                        const next = { ...current };
                        if (event.target.value) next[suggestion.field] = event.target.value;
                        else delete next[suggestion.field];
                        return next;
                      })}
                      value={columnMapping[suggestion.field] ?? ""}
                    >
                      <option value="">不导入</option>
                      {preview.columns.map((column) => <option key={column} value={column}>{column}</option>)}
                    </select>
                  </label>
                ))}
              </div>
              <details className="quality-details">
                <summary>查看列级质量画像</summary>
                <div className="table-panel"><table><thead><tr><th>列名</th><th>空值率</th><th>唯一率</th></tr></thead><tbody>
                  {preview.column_profiles.map((profile) => <tr key={profile.column}><td>{profile.column}</td><td>{(profile.null_rate * 100).toFixed(1)}%</td><td>{(profile.unique_rate * 100).toFixed(1)}%</td></tr>)}
                </tbody></table></div>
                <p>时间解析率：{preview.date_parse_rate === null ? "未映射时间列" : `${(preview.date_parse_rate * 100).toFixed(1)}%`}</p>
              </details>
              {preview.quality_hints.length || preview.quarantine_reasons.length ? (
                <div className="quality-warnings"><AlertTriangle aria-hidden="true" size={16} /><div>
                  {preview.quality_hints.map((hint) => <p key={hint}>{hint}</p>)}
                  {preview.quarantine_reasons.map((item) => <p key={item.reason}>{item.reason}：{item.count} 行</p>)}
                </div></div>
              ) : <p className="quality-ok"><CheckCircle2 aria-hidden="true" size={15} />未发现需隔离的结构问题</p>}
            </div>
          ) : null}
          <div className="form-grid upload-fields">
            <label className="field">来源名称<input maxLength={200} onChange={(event) => setSourceName(event.target.value)} required value={sourceName} /></label>
            <label className="field">渠道<input maxLength={80} onChange={(event) => setChannel(event.target.value)} required value={channel} /></label>
            <label className="field">产品线<input maxLength={120} onChange={(event) => setProduct(event.target.value)} required value={product} /></label>
            <label className="field">分析引擎<select aria-label="分析引擎" onChange={(event) => setAnalysisProvider(event.target.value as AnalysisProvider)} value={analysisProvider}>
              {providers.map((option) => {
                const available = option.configured && option.approved;
                const suffix = option.provider === "local"
                  ? ""
                  : available
                    ? ` · ${option.model ?? "已配置"}`
                    : " · 未配置或未批准";
                return <option disabled={!available} key={option.provider} value={option.provider}>{PROVIDER_LABELS[option.provider]}{suffix}</option>;
              })}
            </select></label>
          </div>
          <div className="upload-card__footer">
            <p><ShieldCheck aria-hidden="true" size={15} />预检只在内存中读取，不写入对象存储或业务表；确认后才导入。</p>
            <div className="upload-actions">
              <button className="button button--secondary" disabled={!file || prechecking || uploading} onClick={runPreview} type="button">
                {prechecking ? "正在预检…" : preview ? "重新预检" : "1. 预检数据"}
              </button>
              <button className="button button--primary" disabled={!mappingReady || uploading || prechecking} type="submit">
                {uploading ? "正在导入并创建任务…" : "2. 确认映射并导入"}
              </button>
            </div>
          </div>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
        </form>

        <aside className="panel pipeline-card" aria-live="polite">
          <p className="eyebrow">处理状态</p>
          <h2>{result?.status === "failed" || result?.status === "dispatch_failed" ? "AI 任务已安全停止" : result?.job_id && result.status !== "succeeded" ? "AI 正在后台分批分析" : result ? "可审核洞察已生成" : uploading ? "后端正在导入" : "等待上传"}</h2>
          <ol className="pipeline-list">
            {["文件校验与留存", "去重与隐私脱敏", "信号抽取与主题聚合", "产品机会草稿"].map((step) => (
              <li className={result ? "is-complete" : uploading ? "is-running" : ""} key={step}>
                <CheckCircle2 aria-hidden="true" size={17} /><span>{step}</span>
              </li>
            ))}
          </ol>
          {result ? (
            <div className="pipeline-result">
              <div><strong>{result.raw_count}</strong><span>原始条数</span></div>
              <div><strong>{result.deduplicated_count}</strong><span>本批入库</span></div>
              <div><strong>{result.cluster_count}</strong><span>主题</span></div>
              <div><strong>{result.opportunity_count}</strong><span>机会草稿</span></div>
              <p><Sparkles aria-hidden="true" size={14} />{result.reused ? "检测到相同文件，已复用既有分析。" : result.notice}</p>
              <p>{result.analysis_provider === "local" ? "本地基线" : `${PROVIDER_LABELS[result.analysis_provider]} · ${result.processed_items ?? 0}/${result.requested_items ?? 0} 条 · ${result.model_calls} 次调用（含重试） · 预留 ¥${(result.reserved_cost_amount ?? 0).toFixed(2)}`}</p>
            </div>
          ) : <p className="pipeline-note">结果会进入决策总览；所有主题与机会保持“待人工复核”，避免把规则基线冒充最终结论。</p>}
        </aside>
      </section>

      <div className="section-heading"><div><p className="eyebrow">批次账本</p><h2>已接入的数据来源</h2></div></div>
      {loading ? (
        <div role="status" className="state-panel">正在核对来源批次…</div>
      ) : (
        <div className="panel table-panel"><table><thead><tr><th>来源</th><th>渠道</th><th>健康状态</th><th>原始</th><th>去重</th><th>隔离</th></tr></thead><tbody>{sources.map((source) => <tr key={source.id}><td>{source.name}</td><td>{source.channel}</td><td>{source.connection_status}</td><td>{source.raw_count}</td><td>{source.deduplicated_count}</td><td>{source.quarantined_count}</td></tr>)}</tbody></table></div>
      )}
    </div>
  );
}
