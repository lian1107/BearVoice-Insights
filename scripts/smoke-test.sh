#!/usr/bin/env bash
# 冒烟测试：这个系统的方向写清楚了没有？
#
# 判据来自 aias-meta-init：新开一个**空会话**，只喂 .42cog/intent.md，问三句——
#   ① 朝哪个方向使劲？ ② 哪些事不做？ ③ 下一步干什么？
# 答不齐 → 方向没写清，回去改 intent.md 那一句。
#
# 为什么必须新开会话：在当前会话里再问一遍没用——它已经读过全部上下文，
# 答得出来是因为记得，不是因为你写清楚了。这里用 claude -p 起一个干净进程。
#
# 用法：bash scripts/smoke-test.sh
# 结果落点：docs/reviews/YYYYMMDD-smoke-test.md
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTENT="$REPO/.42cog/intent.md"
DATE="$(date +%Y%m%d)"
OUT="$REPO/docs/reviews/${DATE}-smoke-test.md"

if [ ! -f "$INTENT" ]; then
  echo "找不到 $INTENT" >&2; exit 1
fi
if ! command -v claude >/dev/null 2>&1; then
  echo "没装 claude CLI，跑不了。" >&2; exit 1
fi

# 提示词落成文件再喂给命令——绝不拼进命令行（CLAUDE.md 第五节）。
PROMPT="$(mktemp -t xbd-smoke)"
trap 'rm -f "$PROMPT"' EXIT

{
  echo "下面是一个项目的意向书全文。**你对这个项目一无所知，只有这一份文件。**"
  echo "请只依据它回答三个问题，答不出来就明确说「这份文件没写清楚」，不要猜、不要补全、不要客气。"
  echo ""
  echo "① 这个系统唯一朝哪个方向使劲？"
  echo "② 明确不做哪些事？"
  echo "③ 拿到这份文件的人，下一步具体该干什么？"
  echo ""
  echo "最后单起一行给判定：三问全部答得出 → PASS；有任何一问答不齐 → FAIL，并指出缺什么。"
  echo ""
  echo "--- 意向书全文 ---"
  cat "$INTENT"
} > "$PROMPT"

echo "▸ 起一个干净会话，只喂 .42cog/intent.md …"
RESULT="$(claude -p < "$PROMPT")"

mkdir -p "$(dirname "$OUT")"
{
  echo "# 冒烟测试 · $(date '+%Y-%m-%d %H:%M')"
  echo ""
  echo "> 判据：新开空会话只喂 \`.42cog/intent.md\`，问三句（朝哪使劲 / 不做什么 / 下一步）。"
  echo "> **答不齐说明方向没写清，回去改 intent.md，不是改这份报告。**"
  echo ""
  echo "## 全新会话的回答"
  echo ""
  echo "$RESULT"
  echo ""
  echo "---"
  echo ""
  echo "*由 \`scripts/smoke-test.sh\` 生成。方向改过之后应当重跑。*"
} > "$OUT"

echo ""
echo "$RESULT"
echo ""
echo "━━ 已存 ${OUT#$REPO/} ━━"
