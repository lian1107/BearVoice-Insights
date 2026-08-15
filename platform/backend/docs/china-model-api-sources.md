# 中国模型 API 接入依据

本模块只使用各提供商的官方文档确认端点和鉴权方式，并统一使用非流式 OpenAI-compatible `POST /chat/completions`。

| Provider | 官方文档 | 默认 base URL |
|---|---|---|
| DeepSeek | https://api-docs.deepseek.com/api/create-chat-completion · https://api-docs.deepseek.com/guides/thinking_mode | `https://api.deepseek.com` |
| 智谱 GLM | https://docs.bigmodel.cn/cn/api/introduction | `https://open.bigmodel.cn/api/paas/v4` |
| MiniMax | https://platform.minimaxi.com/docs/api-reference/text-chat-openai | `https://api.minimaxi.com/v1` |
| 阿里云百炼 / 通义千问 | https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 阿里云百炼地域端点 | https://help.aliyun.com/zh/model-studio/base-url | 由管理员按地域配置 |

## 安全接线条件

只有同时满足以下条件才会外发：

1. `BEARVOICE_MODEL_EGRESS_ENABLED=true`；
2. provider 在 `BEARVOICE_MODEL_PROVIDER_ALLOWLIST` 中；
3. `voice_semantic_analysis` 在 `BEARVOICE_MODEL_PURPOSE_ALLOWLIST` 中；
4. 完整 base URL 在 `BEARVOICE_MODEL_ENDPOINT_ALLOWLIST` 中；
5. 对应 provider 的 API key、base URL 和 model 均由环境变量配置；
6. 载荷通过 `ModelGateway` 隐私门禁。

自定义入口使用 `BEARVOICE_CUSTOM_AI_API_KEY`、`BEARVOICE_CUSTOM_AI_BASE_URL`、`BEARVOICE_CUSTOM_AI_MODEL`；base URL 必须是 HTTPS，且仍必须进入 endpoint allowlist。API key 只从运行环境读取，不进入数据库、请求载荷或网关日志。

## 配置名

| Provider | API key | base URL | model |
|---|---|---|---|
| DeepSeek | `BEARVOICE_DEEPSEEK_API_KEY` | `BEARVOICE_DEEPSEEK_BASE_URL` | `BEARVOICE_DEEPSEEK_MODEL` |
| GLM | `BEARVOICE_GLM_API_KEY` | `BEARVOICE_GLM_BASE_URL` | `BEARVOICE_GLM_MODEL` |
| MiniMax | `BEARVOICE_MINIMAX_API_KEY` | `BEARVOICE_MINIMAX_BASE_URL` | `BEARVOICE_MINIMAX_MODEL` |
| 千问 | `BEARVOICE_QWEN_API_KEY` | `BEARVOICE_QWEN_BASE_URL` | `BEARVOICE_QWEN_MODEL` |
| 自定义 | `BEARVOICE_CUSTOM_AI_API_KEY` | `BEARVOICE_CUSTOM_AI_BASE_URL` | `BEARVOICE_CUSTOM_AI_MODEL` |

allowlist 在 `.env` 中按 JSON 数组传入，例如：

```dotenv
BEARVOICE_MODEL_EGRESS_ENABLED=true
BEARVOICE_MODEL_PROVIDER_ALLOWLIST=["deepseek"]
BEARVOICE_MODEL_PURPOSE_ALLOWLIST=["voice_semantic_analysis"]
BEARVOICE_MODEL_ENDPOINT_ALLOWLIST=["https://api.deepseek.com"]
BEARVOICE_DEEPSEEK_API_KEY=<从密钥管理系统注入>
BEARVOICE_DEEPSEEK_MODEL=deepseek-v4-pro
```

## 主线接口

- `provider_options(settings)`：返回可展示的 provider、是否已配置、是否已批准及 model；不返回密钥或端点。
- `build_model_gateway_from_settings(settings)`：从管理员 allowlist 构建统一 `ModelGateway`。
- `analyze_voice(...)`：分析单条原声，返回严格 `VoiceSemanticResult`，其 `signals` 是零到多条。
- `run_semantic_analysis(...)`：对导入批次创建独立 `AnalysisRun`；每条通过严格校验的结果先按原声 ID、内容哈希、provider、model 和 prompt 版本写入检查点，最终 `Signal`、候选聚类和待审核机会仍原子发布。

DeepSeek V4 Pro 的结构化抽取显式关闭 thinking，并请求 JSON object 响应。模型生成的疑似隐私内容会再次确定性脱敏；纯脱敏占位符不会被当作根因或改进洞察展示。契约连续失败的记录显式进入未解析清单，不伪造结果；网络或进程失败后只补跑未命中检查点的记录。
