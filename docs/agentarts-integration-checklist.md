# AgentArts 联调状态与收尾清单

采集时间：2026-11-07。适用版本：当前 `AI-Lab` 目录。

## 一句话结论

调用链路、输出校验和全部回退路径已经在本机验证通过；**真实云端调用尚未发生**，因为当前没有可用的 AgentArts 账号与 MaaS 模型额度。本文件列出已经证实的部分、仍未证实的部分，以及拿到账号后按顺序执行就能收尾的步骤。

## 已验证 / 未验证

| 项目 | 状态 | 依据 |
| --- | --- | --- |
| 请求头、请求体、SSE 解析与官方接口约定一致 | 已核对文档 | 见下方「契约核对」表，来源为华为云 AgentArts API 文档 |
| 云端分支真的被走到、页面标记为 AgentArts | 已验证（模拟运行时） | `tools/verify_agentarts.py` 的 `ok` 模式：三道题共 72/72 位置 `source=agentarts` |
| 六种云端异常都回退到同级本地提示，页面不报错 | 已验证（模拟运行时） | `waiting` / `error-event` / `http-500` / `bad-json` / `leak-answer` / `slow` 各 72（或 3）位置全部回退，接口错误 0 |
| 终端日志的 `request_id`、`execution_id` 能与运行记录逐条对上 | 已验证（模拟运行时） | `ok` 模式 72 条客户端日志与 72 条运行记录一一匹配 |
| 浏览器实际操作可见 AgentArts 标记，服务停止后自动转为本地规则 | 已验证（模拟运行时） | 手工走查：第 1 步标记 AgentArts，模拟服务停止后第 2 步标记本地规则；修正分母后 4/4 |
| 三道题默认都走云端，开关可收窄到单题 | 已验证（模拟运行时） | 各模式显式设 `AGENTARTS_EXERCISES=average,sum,count`，72 个位置全部走云端；`default-scope` 撤掉开关，三道题各取第 2 级都命中 `agentarts` 且运行时收到 3 条记录；`single-scope` 设 `AGENTARTS_EXERCISES=average`，只有平均值题走云端，载荷回到不带 `exercise_id` 的三项形式，总和题与计数题回到同级本地提示并记 `local_exercise` |
| 三道题的本地提示各说各的量，不互相借词 | 已验证 | `exercise.py` 按题目和诊断类型取词，`tests/test_exercise.py` 钉住总和题不得出现「平均值/分子/分母」、计数题不得把「总和」当答案、平均值题 36 个位置的措辞与已复核基线逐字相同；模拟运行时的题面分支也已移到诊断分支之前 |
| 提示不指向页面上看不到的数 | 已验证 | 数值超限用例的「实际」一栏渲染成 `—`，所以总和题与计数题的第 3 级改成「看你的式子算出的结果比它大了多少倍」，让学生自己算一遍再对照；`tests/test_exercise.py` 与 `tests/test_mock_agentarts.py` 各有一条断言钉住这个写法，模拟运行时求和题的同款文本也已同步 |
| 逐层定位工具本身可信 | 已验证（模拟运行时） | `tools/probe_agentarts.py` 对五种模式分别给出正确判定：`ok` 命中并回显 `execution_id`（退出码 0），`http-500` 报 `http_error`，`error-event` 与 `leak-answer` 报 `invalid_output`，`bad-json` 报 `invalid_response`（退出码 1）；指向不可解析域名时在 DNS 层报 FAIL |
| 回归测试 | 已验证 | `python -B -m unittest discover -s tests` 88 项通过：8 项云端客户端、18 项本地服务、21 项复核统计、15 项判题、10 项模拟运行时离线契约、7 项本机回环真实 HTTP 往返、9 项探针输出与凭据边界；连跑 9 轮无抖动（此前偶发的两次抖动分别来自下面一行的请求体顺序和运行记录落盘时机，均已定位并修掉） |
| 报告里的分子分母与产品规则不再靠手数 | 已验证（真实报告） | `python -B -m evals.score` 重算本地基线为 `evidence_ok 72/72`、`actionable 72/72`、`answer_leaked 0/72`，并逐条校验回退文本、提示格式、`case_id`、`request_id` 与 `summary` 数字 |
| 服务端「先把请求体读完再回应」的约定 | 已验证 | Windows 上先回应、留下未读请求体就断连，会让客户端把 401/413 看成连接错误。`tools/mock_agentarts.py` 与 `app.py` 均改为按 `Content-Length` 声明的长度排空后再发状态码，排空上限统一为 4 MB（`DRAIN_CEILING`）：`app.py` 另有 0.5 秒的排空截止，模拟运行时靠处理器 `timeout = 5` 秒兜底，两者都保证「只报头不发体」的客户端拖不住工作线程。200 KB 这种远超 12 KB 上限的体同样要排干净，`tests/test_app.py`、`tests/test_mock_http.py` 里各有重复多次的真实往返守着这条 |
| 模拟运行时的运行记录早于事件流 | 已验证 | `deliver()` 先把记录写进日志再回放 SSE 事件；反过来的话，客户端读到 `workflow_finished` 时记录可能还没落盘，`tests/test_mock_http.py` 里断言 `records[0]` 的那两条就会随机成功、随机失败 |
| 真实云端提示质量与真实耗时 | **未验证** | 需要已发布的工作流与可用模型额度 |
| 工作流节点配置、试运行、发布与实例部署 | **未验证** | 需要在 AgentArts 控制台手工完成 |
| 真实配对的 `evals/paired-results.json` | **未采集** | 采集方法见文末 |

`evals/mock-paired-results.json` 是模拟数据，报告里的 `note` 字段已注明「非真实云端调用」，其中位耗时约 17 ms 来自本机脚本回放；同一套链路三次采集分别得到约 2 ms、约 16 ms 和约 17 ms，本机抖动本来就大，**不能**用作云端延迟证据。未配置工作流时的接口回退报告同理：两次采集的中位耗时分别是约 1 ms 和约 15 ms，都含本机 HTTP 往返，只说明回退路径可用。

## 契约核对

对照 [工作流 API 调用](https://support.huaweicloud.com/api-agentarts/agentarts_07_0047.html) 与 [响应事件](https://support.huaweicloud.com/api-agentarts/agentarts_07_0056.html) 检查 `agentarts.py`。

| 约定 | 文档要求 | 本项目实现 | 结论 |
| --- | --- | --- | --- |
| 请求行 | `POST /runtimes/{runtime_name}/invocations` | 直接使用控制台复制的完整 HTTPS 地址 | 一致 |
| 入站认证 | `Authorization: Bearer {api_key}` | 同名同格式 | 一致 |
| 会话标识 | `x-hw-agentarts-session-id` | 发送本地生成的 `request_id` | 一致，可据此在控制台检索调用 |
| 请求体 | `{"inputs": {...}}` | 默认 `inputs` 内为 `exercise_title`、`evidence_json`、`hint_level`、`exercise_id`；把 `AGENTARTS_EXERCISES` 收窄为单题时回到前三项 | 一致；文档示例含 `query`，本项目按 README 让 `query` 保持可选且不绑定，见风险 R3 |
| 传输格式 | `text/event-stream` | 逐行读取 `data:` 载荷，上限 128 KB | 一致 |
| 结果位置 | `workflow_finished` → `data.status`（`code=1`、`desc=succeeded`）、`data.outputs.user_fields`、`data.execution_id` | 只接受该组合，其余一律回退 | 一致 |
| 中间事件 | `workflow_started`、`node_started`、`node_finished`、`node_wait`、`message` | 忽略，不拼接进提示 | 一致 |
| 异常事件 | `error`、`exception`、`end` | 立即停止读取并回退 | 一致 |
| 额外请求头 | 文档未列出 | 另发 `X-Request-Id`、`X-Invoke-Mode: published`、`Accept` | **未文档化**，见风险 R2；`python -B tools/probe_agentarts.py --variants` 可在真实端点上一次测出 |

## 本机预验证（不需要账号）

在项目根目录开两个 PowerShell 窗口。第一个跑模拟运行时，第二个跑评测。

```powershell
python -B tools/mock_agentarts.py --port 8931 --mode ok
python -B tools/verify_agentarts.py
```

`verify_agentarts.py` 自己起服务、自己收尾，逐模式打印对照表并在不符预期时以非零退出码报错。期望结果：`ok` 行云端 72、回退 0、错误 0，「logged/calls/execs/matched」为 `72/72/72`；样本表覆盖三道题，这些模式显式带上 `AGENTARTS_EXERCISES=average,sum,count`。其余异常模式的回退数等于位置数，且回退原因与下表吻合；`default-scope` 撤掉开关，应为 3 个云端命中、0 回退、运行时收到 3 条记录；`single-scope` 设 `AGENTARTS_EXERCISES=average`，应为 1 个云端命中加 2 个本地回退、运行记录只有 1 条 `average`。九行全过即输出「9/9 项检查通过」，退出码 0。想手工体验页面，把模拟服务的 URL 和 Key 配进环境变量后启动 `python -B app.py --port 8001`，URL 用 `http://127.0.0.1:8931/runtimes/ai-lab-average/invocations`、Key 用 `dev-mock-key` 即可——只有回环地址允许明文 HTTP，其他地址仍强制 HTTPS。页面现在在任一题目上都会请求提示接口，三道题都能看到 AgentArts 标记。

探针也可以直接指向模拟运行时，用来确认「工具本身的判定可信」，以及演练真实联调时的排查动作：

```powershell
$env:AGENTARTS_WORKFLOW_URL = 'http://127.0.0.1:8931/runtimes/ai-lab-average/invocations'
$env:AGENTARTS_API_KEY = 'dev-mock-key'
python -B tools/probe_agentarts.py            # 期望生产路径 PASS，退出码 0
python -B tools/probe_agentarts.py --url https://example.invalid/runtimes/x/invocations   # 期望逐层 FAIL，退出码 1
```

模拟运行时的提示文本是脚本按证据拼装的，只用于验证链路，不代表模型输出。

## 回退原因对照

后端每条提示都记一行 JSON，`fallback_reason` 为 `null` 表示命中真实云端。真实联调时先看这一列，再决定改哪里。

| `fallback_reason` | 含义 | 首查项 |
| --- | --- | --- |
| `not_configured` | 环境变量缺失 | URL 与 Key 是否在启动服务的同一个 PowerShell 窗口里设置 |
| `local_exercise` | 该题不在 `AGENTARTS_EXERCISES` 名单里，按设计只走本地规则 | 默认三道题都走云端；只有把开关收窄为单题时才会出现，删除该变量即可恢复全部题目 |
| `invalid_endpoint` | 地址非 HTTPS 且非本机回环，或含用户名 | 控制台地址是否复制完整、是否漏了 `https://` |
| `http_error` | 4xx/5xx | Key 是否失效、工作流是否已发布到实例、路径是否为运行时的调用路径 |
| `connection_error` | 连不上、DNS、代理或证书 | 本机浏览器能否打开同一域名，是否需公司代理 |
| `timeout` | 超过 8 秒未拿到结束事件 | 模型耗时；精简提示词或调大 `agentarts._TIMEOUT` |
| `invalid_response` | 事件不是合法 JSON 或结构不符 | 大模型节点是否关闭流式输出、是否选择 JSON 格式 |
| `invalid_output` | `hint` 或 `case_id` 未通过校验 | 结束节点字段名是否为 `hint`/`case_id`、`case_id` 是否取自输入用例、提示是否泄露代码 |

## 拿到账号之后的收尾步骤

1. 开通 AgentArts 并确认有可调用的 MaaS 模型或自有模型额度。API 调用必须有可用额度，这一步没有完成时后面全部无法验证；账号无额度时走赛队共用账号或提交工单申请。
2. 按 [README 的 AgentArts 联调](../README.md#agentarts-联调) 第 1 到 4 步建工作流 `AI-Lab 平均值辅导`，开始节点必须接受字符串 `exercise_id`（`average`、`sum` 或 `count`）。用文档给的失败用例样例试运行，确认结束节点输出 `case_id` 为 `C01` 且 `hint` 是一句中文，再提交版本并部署到实例，开启 API Key 入站认证、日志与调用链。
3. 复制完整 HTTPS 调用路径与运行时 API Key，在本机配置（`Read-Host` 屏蔽输入，变量只对当前窗口及其子进程生效）：

   ```powershell
   $env:AGENTARTS_WORKFLOW_URL = Read-Host '工作流完整 HTTPS 调用地址'
   $env:AGENTARTS_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host '运行时 API Key' -AsSecureString)).Password
   python -B app.py --port 8001
   ```

4. 另开一个 PowerShell 窗口，重复第 3 步的两条 `Read-Host` 设置变量（变量只对当前窗口及其子进程生效），先跑探针再动页面。探针会把配置、DNS、TCP、TLS、HTTP 状态、事件流结构和生产路径逐层分开报告，比在浏览器里反复点提示快得多；`--variants` 顺便验证风险 R2、R3。探针退出码 0 才值得继续，1 时按它指出的层级和上面的回退原因对照表处理。

   ```powershell
   python -B tools/probe_agentarts.py --level 2 --variants
   ```

5. 打开 `http://127.0.0.1:8001`，选任一题目运行预置错误代码，逐级点开提示。三级都应标记 AgentArts；若出现本地规则，按上面的回退原因对照表定位。
6. 用终端日志里的 `request_id` 和 `execution_id` 到控制台执行记录核对同一次调用，确认没有把本地回退误记成云端命中。
7. 把平均值题的分母改成 `len(nums)`（或按各题正确解法修正）重跑，确认通过进度更新，页面与判题仍然正常。
8. 采集真实配对报告，并在 `--note` 里写清工作流版本与模型，便于赛后复核：

   ```powershell
   python -B -m evals.run --compare-port 8001 --output evals/paired-results.json --note "真实云端：工作流版本 X，模型 Y，采集日期 Z"
   ```

9. 按 [评分规则](../evals/README.md) 逐条复核 24 个样本 × 3 级共 72 对，把三个布尔值写回报告的 `review` 字段，分别汇报云端命中、本地回退和接口错误；云端数据不足 72 对时，质量比较只使用真实命中的配对。
10. 打分写回后运行 `python -B -m evals.score evals/paired-results.json --against evals/local-baseline.json --require-complete --json evals/review-summary.json`。退出码 0 才说明分子分母、回退文本、提示格式、`case_id`、`request_id` 和 `summary` 数字全部对得上；`--json` 产出的统计可以直接贴进提交材料。

## 风险与待办

- **R1 额度未确认**：真实云端调用与真实配对报告目前为零证据，任何「已联调」的表述都不成立。
- **R2 未文档化请求头**：`X-Invoke-Mode` 与 `X-Request-Id` 不在官方请求头列表里。`python -B tools/probe_agentarts.py --variants` 会带上和不带这两个头各发一次并对比状态码；若只有去掉它们才通，就从 `agentarts._invoke` 删除，`x-hw-agentarts-session-id` 需保留。
- **R3 `query` 入参**：文档示例把 `query` 放在 `inputs` 里。若开始节点把 `query` 设为必填，本项目的请求会被拒绝并静默回退。`--variants` 会额外发一次带 `query` 的同样载荷做对照；出现「全部三级都是本地规则」时优先检查这一点，或在开始节点把 `query` 改回可选。
- **R4 8 秒上限**：`_TIMEOUT = 8` 覆盖模型排队与两级大模型节点。真实额度紧张时容易超时；探针在拿到事件流时会打印实测耗时，任何情况下只要超过上限都会给出警告，先测几条提示的耗时再决定是否调整。
- **R5 凭据边界**：Key 只放本机环境变量，不写进源码、报告或共享目录。探针只打印 Key 长度，`tests/test_probe.py` 断言输出中不出现 Key 明文。`dev-mock-key` 只是模拟值，不能用于真实调用。
- **R6 复核遗漏**：72 对提示共 144 个打分位置，每格还要填三个布尔值，手工汇总容易把「待复核」当成 `false` 或漏计分母。真实数据采集后先跑 `python -B -m evals.score evals/paired-results.json --against evals/local-baseline.json --require-complete`，它会列出还没打满三项的位置并在缺项时以非零退出码失败；本地侧文本与基准逐条一致时，那一半可沿用基准报告的打分。
- **R7 页面请求范围**（已修复）：`index.html` 原先只替平均值题请求 `/api/hint`，总和题与计数题看不到 AgentArts 标记。现在三道题都会请求，后端按 `AGENTARTS_EXERCISES`（默认全部题目）决定是否出网；未配置或调用失败时仍回退到同级本地提示。
- **待办**：三道题的云端路径已经可用，工作流开始节点需接受 `exercise_id`；真实云端提示质量仍未采集，`evals/paired-results.json` 与其中 144 个打分位置因此都还不存在；服务只监听本机，异地队友需要单独部署；`tools/` 下的模拟、验证与探针脚本不随 `python -B app.py` 启动，也不参与判题。
