# AgentArts.102056 失败排查（P0）

2026-11-10 的 72 次真实调用中，5 次工作流节点失败并回退到本地提示，错误码均为 `AgentArts.102056`。这不是超时、认证失败或本地规则错误，回退路径按设计生效，页面仍可用。

本页只整理可核对的事实与排查步骤；**根因尚未确认**，需在控制台按执行编号查看节点输入输出。

## 失败清单

数据文件：[agentarts-102056-20261110.json](../evals/agentarts-102056-20261110.json)，来源报告 [paired-results.json](../evals/paired-results.json)。

| 样本 | 等级 | 失败节点 | 耗时 | request_id | execution_id |
| --- | --- | --- | --- | --- | --- |
| SU3 | 1 | `node_llm`（诊断） | 2422 ms | `1747780aca5c4e54baf2a3eee55639f8` | `5bf3f5b8-f651-404c-b35b-56f3c6c1f89c` |
| SU3 | 2 | `node_llm`（诊断） | 1297 ms | `83418772f4704a049296b1b73b457707` | `4258af38-3cc5-41b9-8659-e97db856b5b3` |
| CO2 | 2 | `node_1794225680834`（教学提示） | 8531 ms | `7be5f8939859496dbc3aebe2f5c998fa` | `737c96c1-7d8f-4698-93c6-c3fb707d3fc2` |
| CO3 | 2 | `node_llm`（诊断） | 1938 ms | `65536fd4884b4da9aaf0f9a14c6d6866` | `64bb50b6-7ed1-49c1-be5a-411e45ec3f14` |
| CO3 | 3 | `node_llm`（诊断） | 5016 ms | `4f4c68abbc1746609564b1db32ca8139` | `fddab09f-e0e4-45bd-a8d1-1283c908665e` |

观察：

- 4 次失败在诊断节点，1 次在教学提示节点；均发生在进入模型节点之后，结束节点未拿到有效输出。
- 失败耗时 1.3–8.5 秒，明显短于成功样本的中位 9.8 秒，更像节点立即报错而非模型慢响应。
- 失败集中在 `sum`、`count` 两题，但样本量太小，不能据此判断与题目或提示长度相关。

## 控制台排查步骤（需账号登录）

1. 打开 AgentArts 控制台 → 运行时 → 执行记录，按 `execution_id` 逐条检索。
2. 记录失败节点的**输入摘要**（节点输入字段名、`hint_level`、证据长度，不复制完整提示正文）、**错误详情**和**重试次数**。
3. 若错误指向 MaaS：核对模型是否开通、鉴权是否指向当前模型、是否触发调用频率或内容过滤限制。
4. 若错误指向输出解析：核对节点是否关闭流式输出、JSON 格式与字段名是否仍为 `diagnostic_summary`、`case_id`、`hint`。
5. 仅修改与错误直接相关的一项配置，重新发布后只复测 1 次，保存修复前后 `execution_id` 与错误详情。
6. 若 5 次记录的节点输入都含相同的证据结构（例如失败用例的 `actual` 为 `null`），再考虑数据侧问题；不要先改提示词掩盖报错。

## 失败样本小批复测（不重采 72 对）

失败样本已固定为 [agentarts-102056-retest-samples.json](../evals/agentarts-102056-retest-samples.json)：`SU3`、`CO2`、`CO3` 三个样本、9 个提示位置，其中 5 个位置在 2026-11-10 失败。本地侧 9/9 已通过并提供对照报告 [agentarts-102056-retest-local.json](../evals/agentarts-102056-retest-local.json)。

前置条件：服务以 AgentArts 配置启动、进程可出网、`AI_TIMEOUT=60`，并临时关闭提示频率保护；不要在受限沙箱或不可出网的后台进程中执行。命令：

```powershell
python -B -m evals.run --samples evals/agentarts-102056-retest-samples.json --compare-port 8001 --output evals/agentarts-102056-retest-20261111.json --timeout 70 --note "102056 小批复测；真实云端；3 样本 9 位置"
```

判定标准：

- 9 个位置全部 `outcome=cloud` 且 `fallback_rows=0`，才能判定失败样本已恢复；
- 仍有 `workflow_failed` 时，记录新的 `execution_id`、失败节点和耗时，不要先改提示词掩盖报错；
- 小批复测只覆盖失败样本，不能替代 24 样本 / 72 对的完整重采。

复测完成后用以下命令判定，不需要手工数 9 行：

```powershell
python -B tools/check_retest.py evals/agentarts-102056-retest-20261111.json --json evals/agentarts-102056-retest-check.json
```

退出码 0 才表示 9 个位置全部 `outcome=cloud`；非 0 时把缺失或失败位置填入下表。复测报告现在保留 `fallback_reason`、`execution_id`、`cloud_error_code`、`failed_node_id` 等结构化字段，仍不记录模型原始输出。

## 2026-11-11 复测结果

真实云端同进程采集，报告 [agentarts-102056-retest-20261111.json](../evals/agentarts-102056-retest-20261111.json)，判定报告 [agentarts-102056-retest-check.json](../evals/agentarts-102056-retest-check.json)：

- 9/9 `outcome=cloud`，回退 0，错误 0，`check_retest.py` 退出码 0；
- 云端中位 9009.9 ms、P95 21652.5 ms、最长 21652.5 ms；
- 2026-11-10 的 5 个失败位置（SU3 L1/L2、CO2 L2、CO3 L2/L3）本次全部命中云端，`AgentArts.102056` 未复现。

| 复测日期 | 位置 | execution_id | 失败节点 | 耗时 ms | 错误码 | 是否与上次同一节点 | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-11 | SU3 L1 | `4348c6ec-34ab-44ec-8cdb-1b4ee55f1ee9` | 无 | 19288.1 | 无 | 否 | 云端命中 |
| 2026-11-11 | SU3 L2 | `b78166ab-1621-40ae-9b3c-031b44008d90` | 无 | 9698.6 | 无 | 否 | 云端命中 |
| 2026-11-11 | SU3 L3 | `14fe5a1b-93bb-4009-92d1-c7393f3350c5` | 无 | 5497.9 | 无 | 否 | 云端命中 |
| 2026-11-11 | CO2 L1 | `72bb46e1-1161-4c50-8668-37b3c8ecd402` | 无 | 7935.4 | 无 | 否 | 云端命中 |
| 2026-11-11 | CO2 L2 | `7a59d095-a531-4c5a-bc07-a6ad35558b78` | 无 | 21652.5 | 无 | 否 | 云端命中 |
| 2026-11-11 | CO2 L3 | `b09c887a-6e5f-42b4-b786-e9f9ec225987` | 无 | 5856.8 | 无 | 否 | 云端命中 |
| 2026-11-11 | CO3 L1 | `79cd5e06-15a1-4d55-99fc-1261011c7eb3` | 无 | 9009.9 | 无 | 否 | 云端命中 |
| 2026-11-11 | CO3 L2 | `5f4c8eea-e681-40f7-ac39-174802da694c` | 无 | 10648.0 | 无 | 否 | 云端命中 |
| 2026-11-11 | CO3 L3 | `3d2413c6-1232-4c47-8e7c-4e24da99d457` | 无 | 7101.7 | 无 | 否 | 云端命中 |

结论边界：

- `AgentArts.102056` 在这 9 个位置**未复现**，不等于根因已修复；5 条历史执行记录仍需在控制台核对失败节点与错误详情。
- 技术通过不等于提示质量通过。助手初筛发现 CO2 三级仍出现「循环/累加/重复计数」措辞，而该样本代码结构为 `has_loop=false`；SU3 L2/L3 提到「初始累加值」。若控制台尚未发布修订版提示词，本结果应视为旧提示词，不能作为提示质量改善证据。
- 本结果只覆盖 3 样本 / 9 位置，不改变 `evals/paired-results.json` 的 67 对历史口径，也不能替代 24 样本 / 72 对重采与人工复核。

## 2026-11-11 72 对重采

24 样本 / 72 位置重采，报告 [paired-results-after-20261111.json](../evals/paired-results-after-20261111.json)：

- 71 云端命中、1 回退、0 错误；中位 6920 ms、P95 26684 ms、最长 55123 ms。
- 2026-11-10 的 5 个失败位置本次全部恢复；`compare_paired.py` 将它们标为「仅新报告包含」。
- 新增 1 次 `workflow_failed`：SU6 L2，`node_llm`，execution_id `c1e455ea-d3ff-4072-9746-e507914f08e0`，耗时 16955 ms，错误码 `AgentArts.102056`。说明该错误仍偶发，根因未确认。
- 72 条云端提示中未检出「循环/遍历/迭代/累加」措辞（9 位置复测时 CO2 三级仍有）；工作流提示词版本未记录，是否已发布修订版仍需控制台确认。
- 最长 55123 ms 接近 60 秒 `AI_TIMEOUT`，采集与前端超时余量偏小。

## 改善确认后的完整重采

控制台替换提示词并重新发布后，需重采同样的 24 样本 / 72 对，再与修订前报告比较：

```powershell
python -B -m evals.run --compare-port 8001 --output evals/paired-results-after-20261111.json --timeout 70 --note "修订后重采；工作流版本与采集日期"
python -B tools/compare_paired.py evals/paired-results.json evals/paired-results-after-20261111.json --json evals/prompt-revision-compare.json
python -B -m evals.score evals/paired-results-after-20261111.json --against evals/local-baseline.json --require-complete
```

`compare_paired.py` 只比较已复核的云端位置，重采后仍须由队员逐条填写 `evidence_ok`、`actionable`、`answer_leaked`；没有人工签字前，修订效果只能标为「待人工复核」。

## 修复前后证据模板

| 项目 | 修复前 | 修复后 |
| --- | --- | --- |
| 执行编号 | 上表 5 条之一 | 新的 execution_id |
| 错误码 | `AgentArts.102056` | |
| 失败节点 | `node_llm` / 教学提示 | |
| 输入摘要 | | |
| 修改项 | | |
| 结果 | 回退本地提示 | |

## 与产品行为的关系

- 后端把失败归类为 `workflow_failed`，保留 `cloud_error_code`、`failed_node_id`、`execution_id`。
- 前端在 2026-11-10 起显示“云端辅导暂不可用，已使用本地提示”，并保留请求编号。
- 这 5 次不计入云端质量分母；`evals/paired-results.json` 的有效配对为 67 对。
- 修复前不要把 `AgentArts.102056` 写成已解决，也不要把 5 次回退算作“云端成功率 100%”。