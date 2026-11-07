# DeepSeek 临时接入与切回华为 AgentArts

这是本地开发替代通路，不改变华为云 AgentArts 的正式验收口径。DeepSeek 产生的提示不能作为 AgentArts 真实链路证据，正式材料仍需控制台工作流执行记录。

## 本机配置

编辑根目录 `.env`，不要用示例覆盖已有文件，保留原有腾讯与华为参数：

```dotenv
AI_PROVIDER=deepseek
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
AGENTARTS_EXERCISES=average,sum,count
```

1. 在 DeepSeek 开放平台创建 API Key，只填到 `DEEPSEEK_API_KEY`。不要填到 `AGENTARTS_API_KEY`，也不要在聊天、截图或日志里发送真实 Key。
2. 模型先用 `deepseek-chat`。项目要求模型返回单个 JSON 对象（`hint`、`case_id`），并已发送 `response_format={"type":"json_object"}`；`deepseek-reasoner` 对 JSON Output 支持较弱，容易触发 `invalid_response`。
3. `DEEPSEEK_API_URL` 必须是完整 HTTPS 地址，不能带账号、密码或片段，正式验证时不要改成 HTTP。

## 连通性验证

下面这条命令会真实产生 1 次模型调用，并走完整生产路径（配置 → 请求 → JSON 解析 → 输出校验）：

```cmd
cd /d F:\GPT\华为ict
python -B tools/check_deepseek.py --level 2
```

- 退出码 0：`source=deepseek`，同时打印 execution_id、case_id 和提示文本，说明 Key、模型和 JSON 输出都可用。
- 退出码 1：调用或输出校验失败，按打印的 `fallback_reason` 与建议处理。
- 退出码 2：`.env` 未填、`AI_PROVIDER` 不是 `deepseek`，或 Key/模型缺失。

## 启动与页面

```cmd
cd /d F:\GPT\华为ict
python -B tools/start.py --port 8001
```

打开终端显示的地址，提交预置错误并逐级展开提示，来源标记应显示「DeepSeek」。修改 `.env` 后必须重启服务，已有进程环境变量优先于文件。

## 配对评测

服务启动后可采集 DeepSeek 报告。这会产生 72 次模型调用，请先确认额度：

```cmd
python -B -m evals.run --compare-port 8001 --output evals/deepseek-paired-results.json --note "DeepSeek 真实调用：模型、日期、代码版本"
python -B -m evals.score evals/deepseek-paired-results.json --against evals/local-baseline.json --require-complete
```

报告保留 `source=deepseek`，单独命名，不与 AgentArts 或腾讯报告混合；评分前填写云端行的 review 字段。不同服务商分别采集，不要在同一批报告中途切换。

## 切回华为 AgentArts

```dotenv
AI_PROVIDER=agentarts
AGENTARTS_WORKFLOW_URL=工作流完整HTTPS调用地址
AGENTARTS_API_KEY=运行时Key
AGENTARTS_EXERCISES=average,sum,count
```

重启服务后，用控制台执行记录和 `tools/probe_agentarts.py` 重新验收。DeepSeek 与腾讯参数可以保留但不会使用；`AI_PROVIDER` 拼写错误会返回本地规则和 `invalid_provider`，不会自动切换服务商。

## 限制

- 只支持非流式 Chat Completions，不新增 Python 第三方依赖。
- 上游超时默认 8 秒，未做自动重试；真实模型排队时可能回退。
- 输出检查是启发式规则，不能保证识别所有答案泄露，仍需人工评测。
- 当前鉴权、并发和额度保护未达到公网部署标准。