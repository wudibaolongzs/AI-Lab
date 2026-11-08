# 智学工坊 AI-Lab

华为 ICT 创新赛 AgentArts 方向的本地开发原型。学生可选择列表平均值、列表总和或列表元素个数，运行 Python 函数，查看测试证据和分步提示，然后自行修改并复验。

## 启动

本机 `.env` 启动、手机局域网演示和离线测试入口见 [部署与协作说明](docs/local-deployment.md)。

需要 Python 3.9 或更新版本。进入本目录，在 PowerShell 运行：

```powershell
python -B tools/start.py
```

看到终端显示 `AI-Lab 运行中` 后，打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，使用期间保持终端打开。端口占用时可运行 `python app.py --port 8001`，再打开终端显示的地址。按 `Ctrl+C` 停止服务。

## 演示步骤

1. 选择「计算列表平均值」，直接运行编辑区预置的错误代码。观察 `[10, 20, 30, 40]` 的实际值约为 `33.3333`，期望值为 `25.0`。单元素用例会触发除零。
2. 逐次打开三层提示，对照测试证据检查计算方式。
3. 修正分母并重新运行测试。确认该题计入通过进度，再切换到其他题目，查看对应的代码草稿和提交记录。
4. 刷新网页，确认所选题目、草稿、最近五次提交摘要和通过进度仍可查看。这些记录保存在当前浏览器的该站点下。

服务默认监听 `127.0.0.1`；局域网演示可显式设置 --host 和 --allow-host，见部署说明。执行器根据所选题目的函数签名解析抽象语法树，解释白名单内的简单赋值、返回、数值算术和 `sum(nums)`、`len(nums)`。导入、循环、属性访问和任意函数调用会被拒绝。接收完整 Python 程序需要独立的代码执行隔离环境。

## 验证

```powershell
python -B -m unittest discover -s tests -v
```

`GET /api/exercises` 返回题库和各题的初始代码、函数签名。`POST /api/check` 接收 `{"exercise_id":"sum","code":"..."}`，返回判定、用例、诊断和可逐级展示的提示。省略 `exercise_id` 时沿用平均值题，旧 `GET /api/exercise` 接口也可继续使用。

## AgentArts 联调

### 用 .env 保存本地配置

把 `.env.example` 复制为 `.env`，填入工作流完整地址与运行时 Key（Key 不要带 Bearer 前缀），然后运行 `python -B tools/start.py --port 8001`。已存在的环境变量优先于 `.env`，`.env` 已被 `.gitignore` 排除，不要提交。`tools/probe_agentarts.py` 同样读取 `.env`，配置一次即可同时供服务和探针使用。

每条提示现显示来源和请求编号。本地回退会说明未配置、超时、接口错误或输出校验失败。API 的 `fallback_reason` 和 `execution_id` 可用于核对服务日志，真实连接以成功响应和控制台执行记录为准。

手动操作可先看 [逐节点接入指南](docs/agentarts-manual.md)，其中包含可复制的提示词、试运行参数导出和错误排查。

三道题在学生点开某一级提示时都会调用 AgentArts。测试结果由本地执行器计算，云端只接收失败用例和本地诊断。配置缺失、调用失败或输出校验失败时，页面显示同一级「本地规则」提示。默认三道题都走云端；如果账号只发布了一道题的工作流，可设 `AGENTARTS_EXERCISES=average` 把范围收窄到单题，此时请求体回到不带 `exercise_id` 的三项形式。

1. 在 AgentArts 的「开发中心 → 智能体管理 → 工作流」新建 `AI-Lab 平均值辅导`。开始节点配置必填项 `exercise_title`（字符串）、`evidence_json`（字符串）、`hint_level`（整数）和 `exercise_id`（字符串，取值 `average`、`sum` 或 `count`）。默认 `query` 保持可选且不绑定。`evidence_json` 包含 `cases`（失败用例数组）和 `diagnosis`（本地诊断对象）。默认三道题都走云端，请求体因此总带 `exercise_id`；若把 `AGENTARTS_EXERCISES` 收窄为单题，客户端不再发送该字段，请求体回到上面三项。
2. 添加「诊断」大模型节点，关闭节点流式输出，选择 JSON 格式并定义字符串字段 `diagnostic_summary`、`case_id`。在提示词中引用开始节点的 `exercise_title` 和 `evidence_json`。可使用提示词「从输入中的第一个失败用例总结实际结果和期望结果的差异。只引用该用例的 ID。证据不足时指出要验证的假设。只输出含 diagnostic_summary 和 case_id 的 JSON。」
3. 添加「教学提示」大模型节点，关闭节点流式输出，选择 JSON 格式并定义字符串字段 `hint`。引用诊断输出和开始节点的 `hint_level`。可使用提示词「围绕 diagnostic_summary 和 case_id 写一句中文提示。第 1 级提问相关概念，第 2 级指出可以检查的位置，第 3 级提出可执行的排查思路。只在证据给出行号时提及行号。保留学生的修复步骤，避免给出完整代码或可直接粘贴的答案。只输出含 hint 的 JSON。」结束节点将输出参数 `hint`、`case_id` 分别绑定到教学节点和诊断节点的同名字段。
4. 试运行时设置题目为 `计算列表平均值`，等级为 `1`，证据可用下方样例。确认结束节点输出 `case_id` 为 `C01` 且 `hint` 是一句中文。提交版本并部署至实例，使用 API Key 入站认证，开启日志和调用链。从控制台复制完整 HTTPS 调用路径及运行时 API Key。API 调用需要可用的 MaaS 模型或自有模型，请使用账号已有的可调用额度。 [工作流 API 调用](https://support.huaweicloud.com/api-agentarts/agentarts_07_0047.html) · [大模型输出字段](https://support.huaweicloud.com/agentarts_faq/agentarts_09_0023.html) · [结束节点](https://support.huaweicloud.com/lowcode-agentarts/end_node.html)

```json
{"cases":[{"id":"C01","input":[10,20,30,40],"expected":25,"actual":33.333333333333336,"status":"failed"}],"diagnosis":{"kind":"wrong_result","line":3,"message":"用例 C01 的返回值与预期不同。"}}
```

在启动服务的 PowerShell 窗口设置变量。`Read-Host` 会屏蔽 Key 输入，变量在当前进程及其子进程生效。

```powershell
$env:AGENTARTS_WORKFLOW_URL = Read-Host '工作流完整 HTTPS 调用地址'
$env:AGENTARTS_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host '运行时 API Key' -AsSecureString)).Password
python -B app.py --port 8001
```

打开终端显示的实验台地址，提交预置错误并逐级查看提示。页面标为「AgentArts」时，用该条提示的请求编号或终端日志中的 `request_id` 和 `execution_id` 核对真实调用。`POST /api/hint` 接收 `exercise_id`、提交的 `code` 和整数 `level`，返回 `hint`、`case_id`、`source` 和 `request_id`。后端读取 `workflow_finished` 的结构化输出字段。 [响应事件](https://support.huaweicloud.com/api-agentarts/agentarts_07_0056.html)

## 本机预验证（无需云端账号）

没有 AgentArts 账号或模型额度时，用 `tools/mock_agentarts.py` 顶替已发布的工作流。它按官方约定提供 `POST /runtimes/{名称}/invocations`、Bearer Key 校验和 SSE 事件流，把提示装进 `workflow_finished` 的 `outputs.user_fields`。`tools/verify_agentarts.py` 会自行起模拟运行时和 AI-Lab 服务，逐模式采集 72 个评测位置（三道题的 24 条样本各取三级提示）并校验：正常模式真的走云端分支，异常模式全部回退到同级本地提示，且终端日志的 `request_id`、`execution_id` 与运行记录逐条对应。

```powershell
python -B tools/mock_agentarts.py --port 8931 --mode ok   # 另一个窗口运行下一行
python -B tools/verify_agentarts.py
```

样本表覆盖三道题，所以这些模式默认带 `AGENTARTS_EXERCISES=average,sum,count`，请求体因此多出字符串 `exercise_id`，模拟运行时的开始节点校验同样通过。倒数第二行 `default-scope` 撤掉开关，确认默认三道题都走云端、运行时收到三条记录；最后一行 `single-scope` 改为 `AGENTARTS_EXERCISES=average`，确认单题收窄后载荷回到不带 `exercise_id` 的三项形式，总和题与计数题拿同级本地提示并记 `local_exercise`。

拿到调用地址之后，用 `tools/probe_agentarts.py` 一次问清楚是哪一层出了问题。它先检查配置与地址是否安全，再分别报告 DNS、TCP、TLS 的耗时，然后原样发一次调用并逐事件解读返回流，最后走一遍生产路径 `agentarts.get_hint`，复述日志里的 `fallback_reason`。加 `--variants` 会额外验证未文档化请求头和 `query` 字段是否被网关接受。退出码 0 表示生产路径命中云端，1 表示没走到云端——网络层不通或提示已回退，2 表示未配置或地址未通过安全校验。

```powershell
python -B tools/probe_agentarts.py --level 2 --variants                       # 用当前窗口配置的真实地址
python -B tools/probe_agentarts.py --url http://127.0.0.1:8931/runtimes/ai-lab-average/invocations   # 指向模拟运行时，Key 用 dev-mock-key
```

模拟提示由脚本按证据拼装，只验证链路，不代表模型输出；`evals/mock-paired-results.json` 因此不能当作云端证据。契约核对表、回退原因对照与拿到账号后的收尾步骤见 [联调状态与收尾清单](docs/agentarts-integration-checklist.md)。

## 对照评测

运行 `python -B -m evals.run --output evals/local-baseline.json` 可重做本地评测。发布工作流并启动已配置服务后，运行 `python -B -m evals.run --compare-port 8001 --output evals/paired-results.json` 采集配对结果。按评测目录说明评分，分别汇报云端成功、回退和请求失败。

打过分之后用 `python -B -m evals.score evals/paired-results.json --against evals/local-baseline.json --require-complete` 重算分子分母，同时检查报告有没有和产品的提示校验规则矛盾；退出码为 0 才把数字写进材料，统计口径见 [评测目录说明](evals/README.md)。

## 腾讯云临时开发模式

支持通过 `AI_PROVIDER=tencent` 临时使用腾讯云兼容接口，后续设为 `agentarts` 切回华为。配置、来源标记、独立评测及切回步骤见 [腾讯云接入说明](docs/tencent-setup.md)。填写后使用 `python -B tools/start.py` 启动；尚未配置时继续使用本地提示。腾讯结果不作为华为 AgentArts 验收证据。
## DeepSeek 临时开发模式

支持通过 `AI_PROVIDER=deepseek` 使用 DeepSeek 的 OpenAI 兼容接口，适合在华为云工作流发布前验证提示链路。填写 `DEEPSEEK_API_KEY` 与 `DEEPSEEK_MODEL` 后，运行 `python -B tools/check_deepseek.py --level 2` 做一次真实调用；页面来源会标记为「DeepSeek」。配置、独立评测及切回步骤见 [DeepSeek 接入说明](docs/deepseek-setup.md)。DeepSeek 结果同样不作为华为 AgentArts 验收证据。

## 最新状态

队伍信息见 [项目信息](docs/team.md)，采用 [MIT](LICENSE)。进展与待办见 [整改记录](docs/remediation-status.md)。python app.py 不读取 .env，需要配置时使用 tools/start.py。

## 2026-11-08 学习闭环版本

现有8道练习，新增理解变式验证、提示反馈、记录导入导出和可选课堂工作台。完整用法、接口与验收见 [学习闭环说明](docs/learning-guide.md)。新题默认本地辅导；原24样本和72个提示位置保留历史范围。

## 统一题库版本

默认28题，支持分页筛选和维护者JSON题包导入；运行边界与命令见 [统一题库说明](docs/question-bank.md)。原8题与旧报告保持兼容。

## 洛谷精选300题版本

当前总目录328题，其中28道本地教学题、300道洛谷元数据条目。真实远程评测默认关闭；开通与验收条件见 [洛谷接入说明](docs/luogu-guide.md)。未取得完整题面授权前只展示目录与原题链接，不代表已完成真实试交。


教师拍照与资料录入：见 [百度OCR及录题指南](docs/baidu-materials.md)。在 /teacher 创建待审核草稿，人工补齐题包后校验、导出；不会自动发布。百度配置默认关闭。
