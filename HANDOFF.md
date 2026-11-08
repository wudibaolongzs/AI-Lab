# 智学工坊 AI-Lab 队友接手指南

本次整合后的工具、样本范围和验收记录见 [INTEGRATION.md](INTEGRATION.md)。评测脚本已统一使用 24 个样本、72 个提示位置，以下首轮 12 样本说明作为早期联调背景。

这是华为 ICT 创新赛 AgentArts 方向的 Python 编程辅导原型。现有三道练习支持提交、判题、分步提示和修正复验，草稿和进度保存在当前浏览器，三道题的本地提示各按题目和诊断类型给词，不互相借量。三道题都已接入可配置的 AgentArts 调用路径，页面在任一题目点开提示都会请求接口：调用约定已对照官方文档核实，云端分支与全部回退路径可以用 `tools/mock_agentarts.py` 在本机验证通过，不需要账号。默认三道题都走云端，`AGENTARTS_EXERCISES` 可把范围收窄到单题。**仍未完成的是真实云端联调**——当前没有可用的 AgentArts 账号与 MaaS 模型额度，工作流尚未创建发布，真实配对报告也没有采集。拿到地址之后用 `python -B tools/probe_agentarts.py` 逐层定位，状态与收尾步骤见 [联调清单](docs/agentarts-integration-checklist.md)。

## 解压后先跑通本地演示

进入解压后的 `AI-Lab` 目录，用 Python 3.9 或更新版本运行。项目只使用 Python 标准库。

```powershell
python -B -m unittest discover -s tests -v
python -B app.py
```

打开终端显示的地址，默认是 `http://127.0.0.1:8000/`。选择平均值题，运行预置错误代码，应为 0/4。展开三级提示，当前应显示「本地规则」。把分母改成 `len(nums)` 后重跑，应为 4/4。关闭服务可按 `Ctrl+C`。如果端口已占用，用 `python -B app.py --port 8001` 并打开终端显示的地址。

## 第一个开发任务

0. 拿到账号之前，先在一台机器上验证链路：一个窗口运行 `python -B tools/mock_agentarts.py --port 8931 --mode ok`，另一个窗口运行 `python -B tools/verify_agentarts.py`。它逐模式采集 72 个评测位置（三道题的 24 条样本各取三级提示），正常模式应显示云端 72/72，异常模式应全部回退到同级本地提示；最后两行 `default-scope` 确认默认三道题都走云端，`single-scope` 确认 `AGENTARTS_EXERCISES=average` 能收窄到单题，九行全过退出码为 0。这一步不需要任何云端凭据，也不产生云端证据。

1. 按 [README 的 AgentArts 联调步骤](README.md#agentarts-联调)创建工作流，依次配置开始、诊断、教学提示和结束节点。开始节点必须接受字符串 `exercise_id`（取值 `average`、`sum` 或 `count`），默认三道题都会发送该字段。用文档提供的失败用例试运行，确认返回 `hint` 和 `case_id` 后发布。若只发布了一道题的工作流，可在本机设 `AGENTARTS_EXERCISES=average` 收窄范围，此时请求体回到三项形式。
2. 在本机 PowerShell 按 README 输入完整调用地址和运行时 API Key——Key 只在本机终端配置，避免写入源码和共享资料。另开一个窗口同样设置这两个变量，先运行 `python -B tools/probe_agentarts.py --level 2 --variants`，它会逐层报告配置、DNS、TCP、TLS、HTTP 状态、事件流结构和生产路径的结果，退出码 0 才继续。然后启动服务，打开任一题目，确认提示标记为「AgentArts」，并用终端里的 `request_id` 和 `execution_id` 对照控制台执行记录。修正代码后再验证通过进度。
3. 配置云服务并使用 `8001` 端口启动后，在另一个终端运行以下命令。若服务使用其他端口，同步调整 `--compare-port`。

   ```powershell
   python -B -m evals.run --compare-port 8001 --output evals/paired-results.json
   ```

4. 按 [评分规则](evals/README.md)复核 24 个样本、每个三级提示，共 72 对。保留工作流版本、模型、请求编号和汇总，分别记录云端成功、本地回退与接口错误。打完分后用 `python -B -m evals.score evals/paired-results.json --against evals/local-baseline.json --require-complete` 重算分子分母并检查报告与产品规则是否矛盾，退出码 0 才把数字写进材料。如果还拿不到调用配置，可以先复跑本地基线，云端数据等实际联调后再补。

## 改代码时从哪里找

| 文件 | 职责 |
| --- | --- |
| `index.html` | 题目、代码编辑器、提示来源、草稿与进度 |
| `app.py` | 本地 HTTP 服务、题库、判题和提示接口 |
| `exercise.py` | 题库、受限 Python 判题、本地提示 |
| `agentarts.py` | 工作流调用、输出校验和本地回退 |
| `tests/`、`evals/` | 回归测试、固定样本、评测脚本、实测报告和 `evals/score.py` 复核统计 |
| `tools/` | 模拟 AgentArts 运行时、无需账号的本机端到端验证、真实端点的分层诊断探针 |
| `docs/agentarts-integration-checklist.md` | 已验证与未验证项、契约核对表、回退原因对照、收尾步骤 |

两个 HTTP 服务都遵循同一顺序：先把 `Content-Length` 声明的请求体读完，再发状态码。Windows 上带着未读字节关连接会让客户端只看到断连，`401`、`413` 就会变成 `connection_error`。排空量按声明长度取，最多 4 MB（`DRAIN_CEILING`），`app.py` 另设 0.5 秒的排空截止、模拟运行时靠处理器 `timeout = 5` 秒兜底，所以「只报头发体不发」的客户端也拖不住工作线程；新增错误分支时请保持这个顺序，`tests/test_app.py` 与 `tests/test_mock_http.py` 里各有重复多次的真实往返守着它，其中一条专门发 200 KB 的体。模拟运行时的 `deliver()` 也刻意先写运行记录、再回放事件流：反过来的话，测试读到响应时记录可能还没落盘，同一用例会随机通过、随机报错。

完成首轮联调和配对评测后，再按参赛需求扩展题库、MCP、教师端或共享部署。当前服务默认只监听电脑本机，手机同一Wi-Fi可配置 --host/--allow-host，异地访问需受控部署。若继续交给 AI 编程工具，可将本目录设为工作区，并给出任务「先读 HANDOFF.md、README.md 和 docs/agentarts-integration-checklist.md，运行全部测试、`python -B tools/verify_agentarts.py` 与 `python -B -m evals.score evals/local-baseline.json`，确认链路与统计无误后，等账号与 MaaS 额度到位再做真实云端联调并采集真实配对报告」。云端联调的前置条件是账号和模型额度，缺任何一项都只能得到模拟证据。

## 腾讯云临时开发模式

支持通过 `AI_PROVIDER=tencent` 临时使用腾讯云兼容接口，后续设为 `agentarts` 切回华为。配置、来源标记、独立评测及切回步骤见 [腾讯云接入说明](docs/tencent-setup.md)。填写后使用 `python -B tools/start.py` 启动；尚未配置时继续使用本地提示。腾讯结果不作为华为 AgentArts 验收证据。
## DeepSeek 临时开发模式

支持通过 `AI_PROVIDER=deepseek` 使用 DeepSeek 的 OpenAI 兼容接口，用于华为工作流发布前的链路开发与连通性验证。填入 `DEEPSEEK_API_KEY` 与 `DEEPSEEK_MODEL` 后运行 `python -B tools/check_deepseek.py --level 2`，它走完整生产路径并真实消耗一次调用；退出码 0 才说明 Key、模型与 JSON 输出可用。配置、独立评测及切回步骤见 [DeepSeek 接入说明](docs/deepseek-setup.md)。DeepSeek 结果不作为华为 AgentArts 验收证据。

最新整改结果见 [整改记录](docs/remediation-status.md)，不要将历史报告当作当前验收。

## 2026-11-08 学习闭环版本

现有8道练习，新增理解变式验证、提示反馈、记录导入导出和可选课堂工作台。完整用法、接口与验收见 [学习闭环说明](docs/learning-guide.md)。新题默认本地辅导；原24样本和72个提示位置保留历史范围。

## 统一题库版本

默认28题，支持分页筛选和维护者JSON题包导入；运行边界与命令见 [统一题库说明](docs/question-bank.md)。原8题与旧报告保持兼容。

## 洛谷精选300题版本

当前总目录328题，其中28道本地教学题、300道洛谷元数据条目。真实远程评测默认关闭；开通与验收条件见 [洛谷接入说明](docs/luogu-guide.md)。未取得完整题面授权前只展示目录与原题链接，不代表已完成真实试交。
