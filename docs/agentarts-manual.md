# AgentArts 手动接入操作指南

目标是在平均值、总和、计数三道题上都获得带 AgentArts 标记的提示，并能在控制台找到对应执行记录。先在项目根目录运行以下命令，导出与产品相同的真实判题证据，无需配置 Key。

```powershell
python -B tools/probe_agentarts.py --exercise average --level 1 --export-inputs docs/trial-inputs.json
```

## 创建工作流

登录华为云 AgentArts，在「开发中心 → 智能体管理 → 工作流」创建 `AI-Lab 平均值辅导`。选择账号内可用于 API 调用的模型，核对额度与计费。顺序连接「开始 → 诊断 → 教学提示 → 结束」。

开始节点配置下列变量，名称逐字一致。默认三道题都走云端，`exercise_id` 为必填；若把 `AGENTARTS_EXERCISES` 收窄为单题，客户端不再发送该字段，可改回可选。默认 query 设为可选并保持未引用。

| 名称 | 类型 | 必填 |
| --- | --- | --- |
| exercise_title | String | 是 |
| evidence_json | String | 是 |
| hint_level | Integer | 是 |
| exercise_id | String | 是（单题收窄时不需要） |

## 诊断节点

添加大模型节点，命名为「诊断」，关闭流式输出，输出格式选 JSON，定义两个 String 输出 `diagnostic_summary` 和 `case_id`。

系统提示词可复制以下内容。

```text
你是编程实验诊断助手。只依据提供的题目和执行证据分析。
围绕 cases 中第一个失败用例，总结实际值与期望值的差异，或解释已报告的运行异常。
证据不足以确定根因时，提出需要检查的假设，避免断言具体代码错误。
输出原始 JSON，字段为 diagnostic_summary 和 case_id。case_id 必须等于所选失败用例的 id。
```

用户提示词通过控制台变量选择器插入「开始.exercise_title」和「开始.evidence_json」。选择器插入的变量引用应保留为有效引用。

## 教学提示节点

添加大模型节点，命名为「教学提示」，关闭流式输出，输出选 JSON，定义 String 输出 `hint`。

```text
你是启发式编程教师。根据题目、执行证据、诊断和 hint_level 写一句中文提示。
等级 1 提出可检验的概念问题，等级 2 引导核查位置或参与计算的量，等级 3 给出排查与复验方向。
只有执行证据包含行号时才提到行号。保留学生自行修复的步骤。
提示最多 240 字，使用单行纯文本，避免完整函数、return 语句、可直接粘贴的答案表达式和 Markdown 代码块。
输出原始 JSON，只含 hint 字段。
```

用户提示词用变量选择器依次插入「开始.exercise_title」「开始.evidence_json」「诊断.diagnostic_summary」「诊断.case_id」「开始.hint_level」。这样教学节点可以核对原始证据。

结束节点添加输出参数 `hint`，绑定「教学提示.hint」，以及输出参数 `case_id`，绑定「诊断.case_id」。配置在输出参数区域，绑定已解析的字段。指定回复可以引用同名输入参数显示提示，应用使用的是最终结构化输出。 [大模型节点](https://support.huaweicloud.com/lowcode-agentarts/agentarts_05_0062.html) · [结束节点](https://support.huaweicloud.com/lowcode-agentarts/end_node.html)

## 试运行与发布

打开导出的 trial-inputs.json。将 exercise_title、evidence_json、hint_level 和 exercise_id 的值分别填入同名试运行字段。evidence_json 的值是字符串，粘贴解码后的完整 JSON 文本。按等级 1、2、3 分别试运行，确认 hint 为单行文本、case_id 为 C01。再分别用 `sum`、`count` 的试运行参数确认另外两道题的提示措辞没有互相借用。

提交版本时勾选「部署至实例」，入站认证选 API Key，开启日志、指标和调用链。从工作流「调用路径」复制完整 HTTPS 地址，应包含 `/runtimes/…/invocations`。在「托管与运行 → 智能体运行时」中找到对应实例，按「访问与权限控制」获取运行时 API Key。模型调用 Key 与运行时入站 Key 分别用于不同位置。 [官方发布和鉴权步骤](https://support.huaweicloud.com/api-agentarts/agentarts_07_0047.html)

## 连接本地项目

在项目根目录打开 PowerShell，逐行运行。

```powershell
$env:AGENTARTS_WORKFLOW_URL = Read-Host '完整 HTTPS 调用路径'
$env:AGENTARTS_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host '运行时 API Key' -AsSecureString)).Password
python -B tools/probe_agentarts.py --level 1
python -B app.py --port 8001
```

默认三道题都走云端，不需要设置 `AGENTARTS_EXERCISES`。若只发布了一道题的工作流，再设 `$env:AGENTARTS_EXERCISES = 'average'` 收窄范围，此时请求体回到不带 `exercise_id` 的三项形式。Key 输入原始值即可，后端自动添加 Bearer 前缀。探针会发送一次传输检查和一次产品路径调用，可能消耗模型额度。看到生产路径命中云端后，打开 http://127.0.0.1:8001/ ，选择任一题目，提交错误代码并展开提示，确认来源为 AgentArts。修正后重新判题，通过进度应更新。通过终端 request_id 和 execution_id 核对控制台日志。配置环境变量的终端用于启动服务，另一窗口的服务需要重启才能读取新配置。

| 现象 | 排查位置 |
| --- | --- |
| 401/403 | 运行时 Key、入站认证方式、部署状态 |
| 404 | 是否复制了完整 invocations 地址 |
| invalid_output | 最终输出字段名、case_id、提示格式、结束节点绑定 |
| timeout | 模型或工作流耗时，先精简提示词和模型输出 |
| not_configured | 当前启动服务的终端是否设置了两个变量 |

真实联调成功后再按 evals/README.md 采集报告。当前统一样本含三道题，默认三道题都走云端，评分时按实际成功的配对统计。
