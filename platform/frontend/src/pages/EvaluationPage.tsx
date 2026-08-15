import { useEffect, useState } from "react";

import { getGoldenReviewQueue, submitGoldenReview } from "../api/client";
import type { GoldenReviewCommand, GoldenReviewItem } from "../api/types";
import { GoldenReviewQueue } from "../components/GoldenReviewQueue";


export function EvaluationPage({
  loadQueue = getGoldenReviewQueue,
  submitReview = submitGoldenReview,
}: {
  loadQueue?: () => Promise<GoldenReviewItem[]>;
  submitReview?: (id: string, command: GoldenReviewCommand) => Promise<GoldenReviewItem>;
}) {
  const [items, setItems] = useState<GoldenReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadQueue().then(setItems).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "黄金样本队列加载失败"));
  }, [loadQueue]);
  return (
    <div>
      <header className="page-heading"><div><p className="eyebrow">质量中心</p><h1>黄金样本人工定标</h1><p>两人独立审核；分歧进入仲裁，模型建议不等于真相。</p></div></header>
      {error ? <div className="state-panel" role="alert">{error}</div> : items ? <GoldenReviewQueue initialItems={items} submitReview={submitReview} /> : <div className="state-panel" role="status">正在读取定标队列…</div>}
    </div>
  );
}
