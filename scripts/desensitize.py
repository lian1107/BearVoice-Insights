#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客户原声脱敏：把个人信息换成**稳定假名**，然后才允许进 vault/raw/。

为什么不是简单涂黑：分析上必须回答「这三条差评是不是同一个人写的」——
跨 SKU、跨平台聚起来才看得出「一群人」还是「一个人的怪癖」（意向书真难题第三条）。
全涂成 [手机] 就把这个能力一起毁了。所以这里用**加盐哈希假名**：
同一个手机号永远得到同一个 [手机-a3f2]，但从假名反推不回原值。

盐存在 .env.local（永不入库）。**盐丢了，历史批次就对不上号了**——它跟着项目走。

用法：
    python3 scripts/desensitize.py 原始导出.csv -o vault/raw/20260815-tmall-追评/
    python3 scripts/desensitize.py ~/Downloads/导出目录/ -o vault/raw/20260815-客服工单/
    python3 scripts/desensitize.py 某文件.txt --check      # 只报告命中了什么，不写文件

支持 .csv .txt .md .json .tsv（Excel 请先另存为 CSV——xlsx 里的格式和公式不该进真相源）。
"""
import argparse
import csv
import hashlib
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_LOCAL = os.path.join(REPO, ".env.local")
SALT_KEY = "XBD_PSEUDONYM_SALT"
TEXT_EXT = {".csv", ".txt", ".md", ".json", ".tsv"}

# ── 规则表 ───────────────────────────────────────────────────────────────
# 顺序有讲究：先长后短、先具体后笼统。两处踩过的坑：
#   ① 身份证必须排在「长数字串」前，否则 18 位身份证被当订单号吃掉；
#   ② 快递单必须排在订单号前——SF1234567890123 里那串数字会先被订单号规则匹掉，
#      留下 "SF[订单号-xxx]"，快递单规则再也轮不到（2026-08-15 实测复现）。
# 订单号的左边界连字母一起排除，避免再从带前缀的单号中间咬一口。
RULES = [
    ("身份证", re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")),
    ("手机",   re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("邮箱",   re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("固话",   re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")),
    ("快递单", re.compile(r"(?<![A-Za-z0-9])(?:SF|JD|YT|ZT|ST|JT|YD|HT)\d{10,15}(?![A-Za-z0-9])")),
    ("订单号", re.compile(r"(?<![\dA-Za-z])\d{12,24}(?!\d)")),
]

# 地址不做自动替换——正则识别中文地址不可靠，删错了真相源就残了。
# 只标记出来让人看一眼。命中不阻断，但会写进报告。
ADDR_HINT = re.compile(
    r"[一-龥]{2,8}(?:省|自治区)?[一-龥]{2,8}(?:市|自治州)"
    r"[一-龥]{2,10}(?:区|县|市)[一-龥0-9]{2,30}(?:路|街|道|号|栋|幢|单元|室)"
)


def load_salt():
    """从 .env.local 读盐；没有就生成一个并写进去（该文件已被 .gitignore 挡住）。"""
    if os.environ.get(SALT_KEY):
        return os.environ[SALT_KEY]
    if os.path.exists(ENV_LOCAL):
        with open(ENV_LOCAL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(SALT_KEY + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    salt = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    with open(ENV_LOCAL, "a", encoding="utf-8") as f:
        f.write("# 假名盐：同一个人在不同批次里得到同一个假名，靠的就是它。\n")
        f.write("# 丢了它，新旧批次就对不上号了。永不入库，但要跟着项目走（换机器时手动带过去）。\n")
        f.write("%s=%s\n" % (SALT_KEY, salt))
    print("ℹ 新生成了假名盐，已写入 .env.local（不入库）。**换机器时记得把它带上。**")
    return salt


def read_text(path):
    """按 UTF-8 → GBK 的顺序试解码。Windows 导出的 CSV 多半是 GBK 或带 BOM。"""
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(有替换字符)"


def make_pseudonym(kind, value, salt):
    digest = hashlib.sha256((salt + "|" + kind + "|" + value).encode("utf-8")).hexdigest()
    return "[%s-%s]" % (kind, digest[:6])


def scrub(text, salt, stats, mapping):
    for kind, pattern in RULES:
        def repl(m):
            value = m.group(0)
            token = make_pseudonym(kind, value, salt)
            stats[kind] = stats.get(kind, 0) + 1
            mapping.setdefault(kind, set()).add(token)
            return token
        text = pattern.sub(repl, text)
    return text


def scrub_csv_columns(text, columns, salt, stats, mapping):
    """只洗指定列，其余原样保留。

    为什么必须有这个：商品id 是 12 位数字，会被「订单号」规则整片吃掉——
    而它是分析要用的关联键，洗掉了数据就废了（2026-08-15 在赛题数据上实测命中 4295 处误报）。
    结构字段（商品id / 原声id / 链接）留着，只洗客户真正写的那一列。
    """
    buf = io.StringIO(text)
    reader = csv.reader(buf)
    rows = list(reader)
    if not rows:
        return text
    header = rows[0]
    idx = [i for i, h in enumerate(header) if h.strip() in columns]
    missing = columns - {h.strip() for h in header}
    if missing:
        print("      ⚠️ 表头里没有这些列，已跳过：%s" % "、".join(sorted(missing)))
    if not idx:
        return text
    for row in rows[1:]:
        for i in idx:
            if i < len(row):
                row[i] = scrub(row[i], salt, stats, mapping)
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue()


def process(path, out_dir, salt, check_only, columns=None):
    text, enc = read_text(path)
    stats, mapping = {}, {}
    is_csv = os.path.splitext(path)[1].lower() in (".csv", ".tsv")
    if columns and is_csv:
        cleaned = scrub_csv_columns(text, columns, salt, stats, mapping)
    else:
        cleaned = scrub(text, salt, stats, mapping)
    addr_hits = ADDR_HINT.findall(cleaned)

    name = os.path.basename(path)
    total = sum(stats.values())
    detail = "，".join("%s×%d" % (k, v) for k, v in sorted(stats.items())) or "无命中"
    print("  %-40s [%s] %s" % (name, enc, detail))
    if addr_hits:
        print("      ⚠️ 疑似地址 %d 处**未自动替换**（正则认中文地址不可靠，删错了真相源就残了）"
              % len(addr_hits))
        for h in addr_hits[:3]:
            print("         · %s" % h[:40])
        if len(addr_hits) > 3:
            print("         · …还有 %d 处" % (len(addr_hits) - 3))

    if check_only:
        return total, len(addr_hits), 0

    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, name)
    if os.path.exists(dest):
        print("      跳过写入：%s 已存在（只增不删）" % dest)
        return total, len(addr_hits), 0
    with open(dest, "w", encoding="utf-8") as f:
        f.write(cleaned)
    return total, len(addr_hits), 1


def gather(target):
    if os.path.isfile(target):
        return [target]
    files = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for n in sorted(filenames):
            if os.path.splitext(n)[1].lower() in TEXT_EXT:
                files.append(os.path.join(dirpath, n))
    return files


def main():
    ap = argparse.ArgumentParser(description="客户原声脱敏（加盐假名，可跨批次对齐同一个人）")
    ap.add_argument("target", help="要脱敏的文件或目录")
    ap.add_argument("-o", "--out", help="输出目录，通常是 vault/raw/<YYYYMMDD-来源-类型>/")
    ap.add_argument("--check", action="store_true", help="只报告命中什么，不写文件")
    ap.add_argument("--columns", help="CSV 只洗这几列（逗号分隔），如 --columns 原声内容。"
                                      "不给就整篇洗——那会把商品id 之类的结构字段一起毁掉")
    args = ap.parse_args()
    columns = set(c.strip() for c in args.columns.split(",")) if args.columns else None

    if not os.path.exists(args.target):
        print("找不到：%s" % args.target, file=sys.stderr)
        return 1
    if not args.check and not args.out:
        print("要写文件就得给 -o 输出目录（或者加 --check 只看不写）", file=sys.stderr)
        return 1

    files = gather(args.target)
    if not files:
        print("没找到可处理的文件（支持 %s）" % "、".join(sorted(TEXT_EXT)), file=sys.stderr)
        print("Excel 请先另存为 CSV。", file=sys.stderr)
        return 1

    salt = load_salt()
    print("▸ 待处理 %d 个文件" % len(files))
    total_pii = total_addr = written = 0
    for p in files:
        a, b, c = process(p, args.out, salt, args.check, columns)
        total_pii += a
        total_addr += b
        written += c

    print("")
    print("━━ 共替换个人信息 %d 处；疑似地址 %d 处需人工过目 ━━" % (total_pii, total_addr))
    if args.check:
        print("  （--check 模式，没有写任何文件）")
    else:
        print("  写入 %d 个文件到 %s" % (written, args.out))
        print("  下一步：")
        print("    1. 人工抽查两个文件，确认没有漏网的姓名/地址")
        print("    2. bash scripts/backup-vault.sh        备份 + 刷新指针清单")
        print("    3. gitleaks detect --no-git --redact   提交前再扫一遍")
    return 0


if __name__ == "__main__":
    sys.exit(main())
