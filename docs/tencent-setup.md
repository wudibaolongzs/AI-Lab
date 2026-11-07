# 腾讯云临时接入与切回华为

本轮实现的是腾讯混元或 TokenHub 的 OpenAI 兼容 Chat Completions 调用，不是腾讯智能体工作流调用。不新增 Python 第三方运行依赖。尚未填写真实配置或开展付费云端验收。

## 本机配置

编辑根目录 `.env`。已有文件不要用示例覆盖，保留原有华为参数。

```dotenv
AI_PROVIDER=tencent
TENCENT_API_URL=https://api.hunyuan.cloud.tencent.com/v1/chat/completions
TENCENT_API_KEY=
TENCENT_MODEL=
AGENTARTS_EXERCISES=average,sum,count
```

1. 从腾讯云控制台取得同一产品的 API Key、可用模型标识和完整 Chat Completions 地址。填写模型 API Key，不是云账号的 SecretId/SecretKey。不要在聊天中发送密钥。
2. `TENCENT_API_URL` 是完整 HTTPS 地址，必须包含实际的 `chat/completions` 路径，而不是仅填 `/v1`。默认是混元旧平台兼容地址。官方已提示新购模型迁往 TokenHub，新账号需按其控制台提供的地址、模型和对应 Key 填写；不能混用不同产品的 Key。
3. `TENCENT_MODEL` 必须为账号已开通且支持 Chat Completions 的模型标识；代码不擅自指定付费模型。建议优先选择低延迟、能按指令输出 JSON 的文本模型。
4. URL 或 Key 配置本身不代表已接通。运行 `python -B tools/start.py --port 8001`，打开终端地址，提交预置错误后逐级领取提示。现有 PowerShell 环境变量优先于 `.env`；若修改文件未生效，检查旧环境变量并重启服务。

配置为空时不访问腾讯云，页面显示本地规则。成功应显示“腾讯云”并带请求编号；超时、认证失败、JSON 不合格、引用错误用例或完整解法将回退。当前上游请求超时仍为 8 秒，未设置自动重试。输出拦截是启发式检查，真实提示仍需人工评测，不能保证识别所有答案泄露。

## 请求与隐私

云端只接收题目标题、题号、失败用例、结构化诊断和提示等级，不接收学生源码。提示要求为单行不超过 240 字的中文，并返回 hint、case_id。凭据只在后端，日志保留请求编号、来源、耗时、回退原因及可用执行编号，不打印密钥或提示正文。HTTP 重定向不自动跟随。

## 配对评测

在服务已配置并启动后执行以下命令，会实际产生 72 次模型调用，请先确认额度。未配置时运行只会得到本地回退，不是腾讯云实测。

```powershell
python -B -m evals.run --compare-port 8001 --output evals/tencent-paired-results.json --note "腾讯云真实调用：模型、日期、代码版本"
python -B -m evals.score evals/tencent-paired-results.json --against evals/local-baseline.json --require-complete
```

评分前先填写 review 字段，具体规则见 `evals/README.md`。报告逐条保留 `source=tencent`，不计为 AgentArts 验收证据。不同服务商分别采集报告，不要在同一批报告中途切换服务；云端失败回退与成功分别统计。AgentArts 专用探针 `tools/probe_agentarts.py` 不支持腾讯，模拟工具也仍只模拟 AgentArts。

## 切回华为

```dotenv
AI_PROVIDER=agentarts
AGENTARTS_WORKFLOW_URL=工作流完整HTTPS调用地址
AGENTARTS_API_KEY=运行时Key
AGENTARTS_EXERCISES=average,sum,count
```

本机填写实际值后重启启动器。腾讯参数可保留但不会使用。省略 `AI_PROVIDER` 时继续兼容旧行为，默认 AgentArts；拼写错误返回本地规则及 `invalid_provider`，不会自动换用另一家。`AGENTARTS_EXERCISES` 是两家共用的题目范围开关，保留历史名称以兼容现有配置。

切回后用华为专用探针和真实执行记录重新验收，腾讯测试不替代华为工作流验证。当前项目的鉴权、并发和额度保护尚未达到公网部署标准。

## 参考

- 腾讯官方兼容接口说明：https://cloud.tencent.com/document/product/1729/111007
- 本机配置和局域网启动：`docs/local-deployment.md`
