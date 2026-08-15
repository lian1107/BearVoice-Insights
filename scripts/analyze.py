#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客户原声 → 改进机会：四阶段管线。

对应赛题最低成果：
  A 聚类结果 + Top10 反馈类型及占比   → stage cluster
  B ≥3 条改进建议（含优先级排序）      → stage recommend
  C 工作流 Demo                        → 这个脚本本身，分阶段可单独跑给人看

核心判断（整套方法的支点）：**咨询不等于投诉，但咨询同样是改进信号。**
一条「这个怎么清洗」不带情绪，重复几百次就是设计缺陷或说明书缺陷。
所以每条原声先归到四类信号，再谈改法——这一步就是「从客服声音到产品改进建议」的那一跳：

  缺陷 → 产品本身有问题       → 改结构 / 改参数 / 改工艺
  认知 → 不知道怎么用         → 改说明书 / 改交互 / 改开箱引导
  预期 → 买之前就理解错了     → 改详情页 / 改主图 / 改卖点表述
  咨询 → 纯信息询问，无改进信号 → 不计入机会，但计入话务量

用法：
    python3 scripts/analyze.py --list                      看有哪些品类可analyze
    python3 scripts/analyze.py --product 养生壶            跑完整管线
    python3 scripts/analyze.py --product 养生壶 --stage extract   只跑抽取（演示用）
    python3 scripts/analyze.py --product 养生壶 --limit 60  小样本快速验证

LLM 调用走 `claude -p`，每批结果缓存在 _build/，重跑不重算（省额度，也让 Demo 可重放）。
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "vault", "raw", "20260815-赛题资料", "天猫咨询原声-1500条.csv")
BUILD = os.path.join(REPO, "_build", "analyze")
REPORTS = os.path.join(REPO, "reports")

BATCH = 40           # 每批喂给 LLM 的原声条数
SIGNALS = ["缺陷", "认知", "预期", "咨询"]
ADDRESS_MARKER_RE = re.compile(
    r"(?:省|自治区|市|县|区|镇|乡|街道|街|路|巷|村|小区|市场|门口)"
)


# ── 数据 ────────────────────────────────────────────────────────────────
def load_rows(verbose=True):
    """读数据并**按原声id 去重**。

    ⚠️ 源数据 1500 行里只有 1109 个唯一 原声id——282 个 id 各自重复出现，
    且重复行内容一字不差（2026-08-15 实测）。不去重会让总量虚增 35.3%，
    也可能扭曲各反馈类型占比。这是这批数据最容易踩、也最致命的一个坑。
    """
    if not os.path.exists(DATA):
        sys.exit("找不到数据：%s" % DATA)
    with open(DATA, "rb") as f:
        text = f.read().decode("utf-8-sig")
    raw = [r for r in csv.DictReader(io.StringIO(text)) if (r.get("原声内容") or "").strip()]
    key_counts = Counter(r.get("原声id") or r.get("原声内容") for r in raw)

    seen, rows = set(), []
    for r in raw:
        key = r.get("原声id") or r.get("原声内容")
        if key in seen:
            continue
        seen.add(key)
        # <br> 是多轮对话的轮次分隔，换成 / 喂给模型；原件不动
        r["_文本"] = re.sub(r"\s+", " ", (r["原声内容"] or "").replace("<br>", " / ")).strip()
        rows.append(r)

    dropped = len(raw) - len(rows)
    if verbose and dropped:
        duplicated_ids = sum(1 for n in key_counts.values() if n > 1)
        print("ℹ 去重：%d 行 → %d 条（%d 条多余重复行，涉及 %d 个重复 ID；"
              "去重前总量虚增 %.1f%%，各类占比可能偏移）" % (
                  len(raw), len(rows), dropped, duplicated_ids,
                  dropped * 100.0 / len(rows)))
    return rows


def product_key(title):
    """从商品标题里认品类。标题很长且带营销词，靠关键词归类比切词稳。"""
    table = [
        ("养生壶", ["养生壶", "煮茶壶", "烧水壶"]),
        ("电饭煲", ["电饭煲", "电饭锅"]),
        ("内衣洗衣机", ["洗衣机", "清洗机"]),
        ("抽水器", ["抽水器", "吸水器", "压水器", "水泵"]),
        ("破壁机", ["破壁机", "豆浆机"]),
    ]
    for name, kws in table:
        if any(k in title for k in kws):
            return name
    return "其他"


def source_duplicate_stats():
    """Return raw rows, unique IDs, extra duplicate rows, and duplicated IDs."""
    with open(DATA, "rb") as f:
        text = f.read().decode("utf-8-sig")
    raw = [r for r in csv.DictReader(io.StringIO(text))
           if (r.get("原声内容") or "").strip()]
    counts = Counter(r.get("原声id") or r.get("原声内容") for r in raw)
    return {
        "raw_rows": len(raw),
        "unique_ids": len(counts),
        "extra_rows": sum(n - 1 for n in counts.values()),
        "duplicated_ids": sum(1 for n in counts.values() if n > 1),
    }


def sanitize_report_quote(text):
    """Mask address-like dialogue segments before quoting customer text."""
    parts = [part.strip() for part in re.split(r"\s*/\s*", text)
             if part.strip()]
    safe = []
    for part in parts:
        if len(ADDRESS_MARKER_RE.findall(part)) >= 2:
            safe.append("[地址已脱敏]")
        else:
            safe.append(part)
    return " / ".join(safe)


# ── LLM ─────────────────────────────────────────────────────────────────
def cache_path(prompt_text, tag, build_dir=None):
    """Return the stable legacy cache path without reading or writing it."""
    target_dir = build_dir or BUILD
    key = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]
    return os.path.join(target_dir, "%s-%s.json" % (tag, key))


def call_claude(prompt_text, tag):
    """提示词落成文件再喂给命令，不拼进命令行（CLAUDE.md 第五节）。结果按内容哈希缓存。"""
    os.makedirs(BUILD, exist_ok=True)
    cache = cache_path(prompt_text, tag)
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)

    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(prompt_text)
        with open(path, encoding="utf-8") as stdin_f:
            proc = subprocess.run(["claude", "-p"], stdin=stdin_f,
                                  capture_output=True, text=True)
    finally:
        os.unlink(path)

    if proc.returncode != 0:
        sys.exit("claude 调用失败（%d）：%s" % (proc.returncode, proc.stderr[:400]))

    data = extract_json(proc.stdout)
    if data is None:
        sys.exit("模型没给出可解析的 JSON。原始输出前 500 字：\n%s" % proc.stdout[:500])
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def extract_json(text):
    """模型可能在 JSON 前后带解释文字或 ``` 围栏，把最外层的 JSON 抠出来。"""
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1)
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None


# ── 阶段一：抽取 ─────────────────────────────────────────────────────────
EXTRACT_RULES = """你在分析小熊电器天猫客服的**咨询**原声，为产品改进挖掘信号。

**最重要的一条**：咨询不等于投诉，但咨询同样是改进信号。
一条「这个怎么清洗」不带情绪，可它重复出现几百次，就说明产品或说明书有问题。
不要因为语气平和就判成无信号。

给每条原声打四个标签：

1. `signal` —— 信号类型，只能是这四个之一：
   - `缺陷`：产品本身有问题（坏了、糊了、漏了、异响、功能不达标）→ 改结构/参数/工艺
   - `认知`：产品没问题，用户不知道怎么用/不知道正常与否 → 改说明书/交互/开箱引导
   - `预期`：买之前就理解错了（以为有某功能、以为某规格）→ 改详情页/主图/卖点表述
   - `咨询`：纯信息询问，问完就完（发货时间、有没有货、能否开票）→ 无产品改进信号
2. `stage` —— 发生在哪个环节：`售前选购` `使用操作` `清洗保养` `故障异常` `售后物流` `配件耗材`
3. `object` —— 具体指向什么部件或对象，尽量具体：
   例如 `加热盘` `内胆涂层` `密封圈` `滤网` `壶盖` `控制面板` `说明书` `详情页` `App` `赠品配件`。
   实在指不到具体物件就写环节名，别写「产品」这种废话。
4. `issue` —— 一句话说清客户到底卡在哪，**用产品视角而不是复述客户原话**。
   反例：「客户问怎么清洗」。正例：「壶盖与壶身接缝处积垢，用户不知如何拆洗」。

只输出 JSON 数组，每个元素形如：
{"i": 原声序号, "signal": "...", "stage": "...", "object": "...", "issue": "..."}
不要输出任何其它文字。"""


def stage_extract(rows, product):
    out = []
    batches = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]
    for n, batch in enumerate(batches, 1):
        lines = ["%d. %s" % (i, r["_文本"][:300]) for i, r in enumerate(batch)]
        prompt = "%s\n\n品类：%s\n\n--- %d 条原声 ---\n%s" % (
            EXTRACT_RULES, product, len(batch), "\n".join(lines))
        print("  抽取 %d/%d（%d 条）…" % (n, len(batches), len(batch)))
        data = call_claude(prompt, "extract")
        for item in data:
            idx = item.get("i")
            if isinstance(idx, int) and 0 <= idx < len(batch):
                src = batch[idx]
                out.append({
                    "signal": item.get("signal", "咨询"),
                    "stage": item.get("stage", ""),
                    "object": item.get("object", ""),
                    "issue": item.get("issue", ""),
                    "原声": src["_文本"],
                    "原声id": src.get("原声id", ""),
                    "情感": src.get("原声情感", ""),
                    "日期": src.get("原声日期", "")[:10],
                })
    return out


# ── 阶段二：聚类 ─────────────────────────────────────────────────────────
CLUSTER_RULES = """下面是同一品类客服咨询的抽取结果，每行是一条原声的标签。

把它们**归并成互斥的反馈类型**（目标 8–12 类，覆盖尽量全）。归并要求：

- 同一个根因归成一类，哪怕用户说法不同。
  例如「怎么清洗」「缝里有垢」「拆不下来洗」→ 同一类：清洗结构不易拆洗。
- 类名要能直接写进产品改进单，**含指向的对象 + 问题**，8–20 字。
  反例：「清洗问题」。正例：「壶盖接缝积垢且无法拆卸清洗」。
- 一个类只能有一个主 signal（缺陷/认知/预期/咨询），按该类里最主要的那个定。
- `咨询` 类信号也要归类（它反映话务量），但标明无改进信号。

只输出 JSON 数组，每个元素：
{"name": "类名", "signal": "缺陷|认知|预期|咨询", "object": "主要指向", "members": [行号...]}
每一行号只能归进一个类，不要遗漏行号。不要输出任何其它文字。"""


def stage_cluster(records, product):
    lines = ["%d. [%s|%s|%s] %s" % (i, r["signal"], r["stage"], r["object"], r["issue"])
             for i, r in enumerate(records)]
    prompt = "%s\n\n品类：%s\n\n--- %d 行 ---\n%s" % (
        CLUSTER_RULES, product, len(lines), "\n".join(lines))
    print("  聚类 %d 条抽取结果…" % len(records))
    clusters = call_claude(prompt, "cluster")

    total = len(records)
    for c in clusters:
        members = [i for i in c.get("members", []) if isinstance(i, int) and 0 <= i < total]
        c["members"] = members
        c["count"] = len(members)
        c["pct"] = round(len(members) * 100.0 / total, 1) if total else 0.0
        c["情感分布"] = dict(Counter(records[i]["情感"] for i in members))
    clusters.sort(key=lambda c: -c["count"])
    return clusters


# ── 阶段三：建议 ─────────────────────────────────────────────────────────
RECOMMEND_RULES = """下面是一个品类客服咨询的聚类结果，按咨询量从多到少排列。
为其中**有改进信号的类**（signal 不是「咨询」）写产品改进建议。

每条建议必须给出：

- `cluster`：对应的类名，照抄
- `action`：具体改什么。**必须落到可执行的动作**，不是方向口号。
  反例：「优化清洗体验」。正例：「壶盖改为可拆卸两段式结构，密封圈独立可取出」。
- `type`：改动类型，`结构改动` `参数调整` `工艺材料` `说明书/包装` `详情页/主图` `软件交互` 之一
- `effort`：改动成本，`低`（改文案/说明书，天级）`中`（软件或小结构，月级）`高`（开模/重新设计，季度级）
- `impact`：影响面，直接用该类咨询量占比
- `priority`：优先级 `P0` `P1` `P2`。判据——
  P0 = 咨询量大且 effort 低（马上能改、马上见效，先摘这个）
  P1 = 咨询量大但 effort 高（真问题，要立项）或 量中等且 effort 低
  P2 = 其余
- `why`：为什么这么判，一句话，要引用数据（占比、情感分布）

**按 priority 再按影响面排序输出。** 只输出 JSON 数组，不要任何其它文字。"""


def stage_recommend(clusters, product, records):
    payload = [{"name": c["name"], "signal": c["signal"], "object": c.get("object", ""),
                "count": c["count"], "pct": c["pct"], "情感分布": c["情感分布"],
                "样本": [records[i]["issue"] for i in c["members"][:5]]}
               for c in clusters if c["signal"] != "咨询"]
    prompt = "%s\n\n品类：%s\n\n--- 聚类结果 ---\n%s" % (
        RECOMMEND_RULES, product, json.dumps(payload, ensure_ascii=False, indent=1))
    print("  生成改进建议（%d 个有信号的类）…" % len(payload))
    return call_claude(prompt, "recommend")


# ── 阶段四：出报告 ───────────────────────────────────────────────────────
def write_report(product, rows, records, clusters, recs):
    slug = "improve-%s" % product
    outdir = os.path.join(REPORTS, slug)
    os.makedirs(outdir, exist_ok=True)
    total = len(records)
    sig_count = Counter(r["signal"] for r in records)
    actionable = total - sig_count.get("咨询", 0)
    duplicate_stats = source_duplicate_stats()
    duplicate_inflation = (duplicate_stats["extra_rows"] * 100.0 /
                           duplicate_stats["unique_ids"])

    L = []
    A = L.append
    A("# %s · 客户原声聚类与产品改进建议" % product)
    A("")
    A("> 数据：`vault/raw/20260815-赛题资料/天猫咨询原声-1500条.csv`（天猫客服咨询，2026-08-01 ~ 08-03）")
    A("> 本品类 **%d 条**（已按 `原声id` 去重），其中含产品改进信号 **%d 条（%.0f%%）**。"
      % (total, actionable, actionable * 100.0 / total))
    A("> ⚠️ **源数据 %d 行中有 %d 条多余重复行，涉及 %d 个重复 ID**；"
      "去重前总量虚增 %.1f%%，各类占比也可能偏移。本报告的数字是去重后的。" % (
          duplicate_stats["raw_rows"], duplicate_stats["extra_rows"],
          duplicate_stats["duplicated_ids"], duplicate_inflation))
    A("> 由 `scripts/analyze.py` 生成，可重跑复现。")
    A("")
    A("## 一、信号构成")
    A("")
    A("咨询不等于投诉。把「问什么」翻译成「该改什么」，先分四类信号：")
    A("")
    A("| 信号 | 含义 | 条数 | 占比 | 对应改法 |")
    A("|---|---|---:|---:|---|")
    meaning = {"缺陷": ("产品本身有问题", "改结构 / 参数 / 工艺"),
               "认知": ("用户不知道怎么用", "改说明书 / 交互 / 开箱引导"),
               "预期": ("买之前就理解错了", "改详情页 / 主图 / 卖点表述"),
               "咨询": ("纯信息询问", "无产品改进信号，计入话务量")}
    for s in SIGNALS:
        n = sig_count.get(s, 0)
        m = meaning[s]
        A("| **%s** | %s | %d | %.1f%% | %s |" % (s, m[0], n, n * 100.0 / total, m[1]))
    A("")
    A("## 二、Top%d 反馈类型及占比（赛题成果 A）" % min(10, len(clusters)))
    A("")
    A("| # | 反馈类型 | 信号 | 指向 | 条数 | 占比 |")
    A("|---:|---|---|---|---:|---:|")
    for i, c in enumerate(clusters[:10], 1):
        A("| %d | %s | %s | %s | %d | **%.1f%%** |" % (
            i, c["name"], c["signal"], c.get("object", ""), c["count"], c["pct"]))
    A("")
    A("## 三、产品改进建议（赛题成果 B）")
    A("")
    A("优先级判据：**咨询量（影响面）× 改动成本**。"
      "P0 = 量大且改起来便宜，先摘；P1 = 量大但要立项，或量中等而便宜；P2 = 其余。")
    A("")
    for i, r in enumerate(recs, 1):
        A("### %s · %d. %s" % (r.get("priority", "P?"), i, r.get("action", "")))
        A("")
        A("- **对应反馈类型**：%s（%s）" % (r.get("cluster", ""), r.get("impact", "")))
        A("- **改动类型**：%s ｜ **成本**：%s" % (r.get("type", ""), r.get("effort", "")))
        A("- **判断依据**：%s" % r.get("why", ""))
        A("")
    A("## 四、证据附录")
    A("")
    A("每个反馈类型抽 3 条原声为证。完整成员见 `_build/analyze/` 缓存。")
    A("")
    for c in clusters[:10]:
        A("**%s**（%d 条，%.1f%%）" % (c["name"], c["count"], c["pct"]))
        A("")
        for i in c["members"][:3]:
            A("> %s" % sanitize_report_quote(records[i]["原声"])[:180])
            A(">")
            A("> — `%s` ｜ %s ｜ %s" % (records[i]["原声id"][:16], records[i]["情感"], records[i]["日期"]))
            A("")
    A("---")
    A("")
    A("*由 `scripts/analyze.py` 生成。重跑：`python3 scripts/analyze.py --product %s`*" % product)

    path = os.path.join(outdir, "报告.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    with open(os.path.join(outdir, "聚类明细.json"), "w", encoding="utf-8") as f:
        json.dump({"product": product, "total": total, "clusters": clusters,
                   "recommendations": recs}, f, ensure_ascii=False, indent=1)
    return path


# ── 主流程 ──────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="客户原声 → 改进机会 管线")
    ap.add_argument("--product", help="品类名，见 --list")
    ap.add_argument("--list", action="store_true", help="列出可分析的品类与条数")
    ap.add_argument("--stage", choices=["extract", "cluster", "recommend", "all"],
                    default="all", help="只跑到某一阶段（演示用）")
    ap.add_argument("--limit", type=int, help="只取前 N 条（快速验证用）")
    args = ap.parse_args()

    rows = load_rows()
    for r in rows:
        r["_品类"] = product_key(r.get("商品标题", ""))

    if args.list or not args.product:
        print("可分析品类：")
        for name, n in Counter(r["_品类"] for r in rows).most_common():
            print("  %-12s %4d 条" % (name, n))
        print("\n用法：python3 scripts/analyze.py --product 养生壶")
        return 0

    subset = [r for r in rows if r["_品类"] == args.product]
    if not subset:
        sys.exit("没有这个品类：%s（跑 --list 看有哪些）" % args.product)
    if args.limit:
        subset = subset[:args.limit]
    print("▸ %s：%d 条" % (args.product, len(subset)))

    print("▸ 阶段一 抽取")
    records = stage_extract(subset, args.product)
    print("  得到 %d 条结构化标签" % len(records))
    if args.stage == "extract":
        print(json.dumps(records[:5], ensure_ascii=False, indent=1))
        return 0

    print("▸ 阶段二 聚类")
    clusters = stage_cluster(records, args.product)
    print("  归并成 %d 个反馈类型" % len(clusters))
    if args.stage == "cluster":
        for c in clusters:
            print("  %5.1f%%  %-34s [%s] %d 条" % (c["pct"], c["name"], c["signal"], c["count"]))
        return 0

    print("▸ 阶段三 建议")
    recs = stage_recommend(clusters, args.product, records)
    print("  %d 条建议" % len(recs))
    if args.stage == "recommend":
        print(json.dumps(recs, ensure_ascii=False, indent=1))
        return 0

    print("▸ 阶段四 出报告")
    path = write_report(args.product, subset, records, clusters, recs)
    print("\n━━ %s ━━" % os.path.relpath(path, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
