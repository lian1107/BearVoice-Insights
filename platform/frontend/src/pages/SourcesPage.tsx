import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, FileSpreadsheet, ShieldCheck, Sparkles, Upload } from "lucide-react";

import { getSources, uploadVoiceCsv } from "../api/client";
import type { SourceSummary, UploadAnalysisResult, UploadSourceCommand } from "../api/types";


export function SourcesPage({
  uploadCsv = uploadVoiceCsv,
  loadSources = getSources,
}: {
  uploadCsv?: (file: File, command: UploadSourceCommand) => Promise<UploadAnalysisResult>;
  loadSources?: () => Promise<SourceSummary[]>;
}) {
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [sourceName, setSourceName] = useState("路演文件上传");
  const [channel, setChannel] = useState("天猫");
  const [product, setProduct] = useState("养生壶");
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

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("请先选择 CSV 文件");
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
        productColumn: "商品标题",
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
            <div><p className="eyebrow">路演可用 · 无需模型密钥</p><h2 id="upload-title">上传 CSV 并生成分析基线</h2></div>
          </div>
          <label className="file-drop">
            <FileSpreadsheet aria-hidden="true" size={28} />
            <strong>{file?.name ?? "选择客户原声 CSV"}</strong>
            <span>UTF-8 编码，最大 10 MB；必需列：原声id、原声内容、商品标题</span>
            <input accept=".csv,text/csv" aria-label="客户原声 CSV" onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" />
          </label>
          <div className="form-grid upload-fields">
            <label className="field">来源名称<input maxLength={200} onChange={(event) => setSourceName(event.target.value)} required value={sourceName} /></label>
            <label className="field">渠道<input maxLength={80} onChange={(event) => setChannel(event.target.value)} required value={channel} /></label>
            <label className="field">产品线<input maxLength={120} onChange={(event) => setProduct(event.target.value)} required value={product} /></label>
          </div>
          <div className="upload-card__footer">
            <p><ShieldCheck aria-hidden="true" size={15} />原文进入本地对象存储；分析前自动脱敏，模型调用为 0。</p>
            <button className="button button--primary" disabled={uploading} type="submit">
              {uploading ? "正在清洗与分析…" : "上传并开始分析"}
            </button>
          </div>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
        </form>

        <aside className="panel pipeline-card" aria-live="polite">
          <p className="eyebrow">处理状态</p>
          <h2>{result ? "分析基线已生成" : uploading ? "后端正在处理" : "等待上传"}</h2>
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
