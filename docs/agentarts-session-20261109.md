# AgentArts 接入进度记录（2026-11-09）

状态：草稿已保存，未提交版本、未部署；用户要求暂停后续云端测试。此行为 2026-11-09 当时状态，2026-11-10 的部署、复测与验收结果见文末两节。
工作流：AI-Lab 编程辅导（对话型）。控制台最后确认保存于 22:46:46。

## 已完成

- 流程为：开始 → 诊断 → 教学提示 → 代码 → 结束。
- 代码节点输入引用教学提示.hint、诊断.case_id；仅校验并返回字段，不执行学生代码。
- 结束节点输出 hint、case_id 均引用代码节点对应字段。
- 教学节点多余的 raw_output JSON 字段已删除，仅保留 hint。
- evidence_json 默认值已换成由本地判题器导出的平均值失败证据，替换占位文字。
- 对话型的 query 被平台锁定为必填。新增可选 AGENTARTS_QUERY：非空时由适配器和探针发送；留空时保留旧请求字段。本机 .env 已添加固定教学请求说明，但尚未切换 AI_PROVIDER，尚无运行时调用地址或 API Key。
- 本地适配器及探针 23 项测试通过；该结果属于离线测试，不是真实运行时 API 验收。

## 本次真实控制台试运行

1. 失败，10.18 秒。诊断成功；教学节点提示 Missing required property 'raw_output'。已删除该多余字段。
2. 失败，8.56 秒。重新开启试运行后使用了默认占位证据，诊断无法返回有效 case_id，导致流程中断。教学节点已成功；其字段冲突不再出现。默认证据现已修正，尚未再次验证。

未获得完整流程成功结果，也没有发布运行时 API 成功证据。不能把本次记录写为真实接入验收通过。

## 下次继续

1. 开始新的试运行前，逐项核对 exercise_title、evidence_json、hint_level、exercise_id；证据必须包含真实 cases，不能是占位文字。对话型进入聊天窗口后还需发送 query。
2. 取得新的调用额度授权后，仅复测一次；检查最终 hint 为非空短中文提示、case_id 为 C01，代码和结束节点均成功。
3. 成功后提交版本并部署至实例；API Key 入站认证，开启日志、指标、调用链。涉及新凭据由用户本人操作。
4. 本机 .env 填入完整 HTTPS AGENTARTS_WORKFLOW_URL 与运行时 AGENTARTS_API_KEY，AI_PROVIDER 改为 agentarts；不要把 IAM AK/SK 填入 API Key。
5. 工作流当前要求 exercise_id 必填，保持 AGENTARTS_EXERCISES=average,sum,count；若收窄到单题，先同步调整开始节点的 exercise_id 必填设置。
6. 核对 AI_TIMEOUT。已观测失败流程超过默认 8 秒，初次接通可用 30 秒，再根据成功实测确定。
7. 获得新授权后运行 probe_agentarts.py。探针会产生两次工作流调用；通过后再做网页、等级 2/3 和其他题目验收。

官方说明：https://support.huaweicloud.com/api-agentarts/agentarts_07_0047.html

## 2026-11-10 部署状态更新

- 已在控制台确认部署成功；运行时状态正常，认证为 API Key。
- 运行时：agent-arts-e3f37c13f413457fa08696abc3d3b7b6，访问方式 Latest，运行时版本 v1。
- 已将控制台显示的 HTTPS 调用地址及自动生成的运行时 API Key 写入本机 .env；凭据不写入此文档。
- AI_PROVIDER 已切为 agentarts，AI_TIMEOUT=30，AGENTARTS_QUERY 已配置；.env 由 Git 忽略。
- 23 项适配器与探针离线测试通过。本轮尚未发起真实 API 调用，等待单次调用授权；部署成功不等于教学输出验收通过。
- 原有服务进程需重启，推荐使用 python -B tools/start.py --port 8001 加载 .env。

## 2026-11-10 首次真实 API 实测

- 用户单独授权沙箱外一次调用，实际请求次数 1，无重试。
- HTTP 200，Content-Type 为 text/event-stream; charset=utf-8，耗时 1828 ms。
- 产品路径返回 source=local，fallback_reason=invalid_output，execution_id=null。
- request_id：482fe5f509e34e79acb5e42774b58cd7，可用于后续云端追踪。
- 该结果只能证明 HTTP 传输返回正常，不能证明工作流执行成功或最终提示合格。
- 随后只读查看运行时日志，近 1 小时无匹配数据。尚无法区分上游节点失败与事件格式兼容问题，不据此改动解析器或放宽输出校验。
- 原始 SSE 本次未留存；仅保存了安全的 HTTP 元信息与生产路径返回，报告见 evals/agentarts-real-single-call-20261110.json。
- 后续先关联已有云端记录；若需要再次请求，先获得新的单次调用授权，并同步采集经过脱敏的事件结构和失败原因，避免为诊断而重复请求。

## 2026-11-10 只读失败原因排查

- 本轮没有重新调用模型，没有修改工作流、凭据或解析器。
- 运行时日志扩大到近 1 天仍无数据；观测的调用链分析已从默认单智能体改为工作流，并选中 AI-Lab 编程辅导，仍无匹配记录。
- 核对官方响应事件文档：成功 workflow_finished 状态为 code=1、desc=succeeded，最终字段位于 outputs.user_fields。本地成功条件与文档一致，尚无证据支持放宽格式。
- 确认本地诊断缺陷：agentarts.py:68 遇到 error/exception 即停止，未保留错误详情；失败 workflow_finished 也返回 None,None；get_hint 最终统一标记 invalid_output。
- 离线合成事件验证：云端 error、失败 workflow_finished、成功但缺少最终字段，都会返回 invalid_output。前两种还丢失可追踪执行信息。合成验证不是真实云端结果。
- 因首次 API 响应原始 SSE 没有保存、现有云端记录不可查询，本次真实失败根因尚无法确定。不能断言是模型 Key、额度、JSON 字段或具体节点错误。
- 下一步应先补脱敏事件诊断采集（事件类型、错误码、失败节点、执行编号、最终字段名称，不记录 Key 或推理正文），再在用户单独授权后发起一次请求，同时保存响应摘要。不要先盲改工作流或放宽提示校验。

## 2026-11-10 已定位真实失败原因

- 本轮在用户“继续排除直到成功”的授权下，执行一次带脱敏事件采集的真实请求，无自动重试。
- 云端进入 workflow_started 后，在 node_llm（诊断）节点失败：AgentArts.100025 / Model request failed。
- MaaS 原始错误：ModelArts.81002 / Failed to get the authorization header.
- 云端执行编号：886b9e17-5e1d-4e5e-826e-6f5016c41433；请求编号：40b940b7fb54414b933ee443fbf7ca24。
- 最终状态 failed，未执行到教学提示、代码和结束输出，故本次不是最终提示格式问题。
- 官方错误码说明：Authorization 为空或缺少 Bearer 前缀。出错链路为 AgentArts 到 MaaS；本机到运行时的认证已放行，不能用更换本机运行时 Key 解决。
- 控制台“授权管理 → 模型”显示当前 DeepSeek-V4.1-Flash-1017 未开通；“云服务”页也显示 MaaS 模型服务未开通。模型开通/鉴权尚未正确完成。
- 已打开模型开通窗口，仅当前 DeepSeek 被选中；其他模型、自动开通新模型、协议均未选中。未代用户接受服务声明或执行开通。
- 用户必须亲自核对按需费用、服务声明及暂不支持关闭服务说明，完成开通，再在鉴权管理中配置正确 MaaS 模型 API Key。无需把 Key 发到聊天中。完成后继续复测并核对是否还存在后续节点问题。
- 本地最小修复：将失败事件区分为 workflow_failed，并保留格式受限的 cloud_error_code、failed_node_id、execution_id；不记录原始错误正文，不改变成功输出/完整答案校验。
- 两项新回归测试先失败后通过；适配器、探针、额度保护相关 32 项测试通过。完整离线回归另行记录。

事件报告：evals/agentarts-diagnostic-20261110.json。
官方错误码：https://support.huaweicloud.com/model-call-maas/model-call-035.html
模型开通与鉴权：https://support.huaweicloud.com/bestpractice-agentarts/agentarts_06_0095.html
- 完整离线回归最终结果：Ran 213 tests，OK (skipped=40)，其中网络测试按离线模式跳过；git diff --check 通过。旧模拟协议测试已同步为失败事件抛出 WorkflowFailure 的诊断契约，成功解析与本地回退保持不变。
- 账号侧模型开通协议与凭据填写需要用户手动完成。已保留开通页面，待用户完成后继续真实复验，不将当前状态记为成功。

## 2026-11-10 授权后复测与成功验收

1. 用户完成模型开通后首次复测仍返回 ModelArts.81002；执行编号 16669702-52da-4927-8cce-a4b2858243db。控制台模型为已开通，鉴权管理存在保存的密钥配置（未读取其值）。
2. 更新原运行时并同步当前模型鉴权，发布版本 v20261110204344。复测工作流成功、source=agentarts，耗时 11187 ms，但提示编造了用例列表/期望值，因此仅为技术通过，教学质量不通过。报告单独保存在 agentarts-transport-passed-quality-failed-20261110.json。
3. 最小调整教学系统提示词：禁止复述具体数值/列表、禁止质疑判题标准，等级 1 仅提出一个概念问题，不提供公式。保存并发布 v20261110204946，同步更新原运行时，控制台确认部署成功。
4. 修正后真实 API 复测通过，耗时 7703 ms，status={code:1,desc:succeeded}，输出字段 hint、case_id 均有效；source=agentarts，case_id=C01，fallback_reason=null。
5. request_id=f681e05725874980b3b2f35f129c6fdb，execution_id=be143b3b-82a6-441b-8561-7a89bb4ecf21。
6. 返回提示：想一想：平均值表示把总量平均分给多少个对象，那么分母应当对应其中的哪一数量？
7. 助手核对本条提示符合平均值概念、未编造具体用例、未泄露完整解法。此为助手辅助检查，不是人工配对评分，不代表全部题目教学质量通过。
8. 正确平均值函数经本地同一判题器复验 4/4 通过。没有继续发起云端调用。

本轮结论：平均值题一级提示的真实 AgentArts 链路已跑通；其余级别、sum/count、网页操作和72对评测仍需后续单独验收。
成功报告：evals/agentarts-diagnostic-20261110.json。
本机配置仍为 AI_PROVIDER=agentarts、AI_TIMEOUT=30；已运行的旧服务需用 tools/start.py 重启才能加载 .env。
## 2026-11-10 三题三级与 72 对采集

1. 修复验收阻塞：`tools/probe_agentarts.py` 在 `load_env` 后调用 `agentarts.refresh_timeout()`，不再固定使用导入时的 8 秒；前端提示等待上限由 18 秒调到 65 秒，避免 20–35 秒的真实响应被 abort 后误显示本地规则。
2. 平均值、总和、计数三题各 1–3 级，通过网页真实调用共 9 个位置，全部标记「AgentArts」，`case_id` 分别为 C01、S01、N01，与本地判题的首个失败用例一致；三题正确写法各自 4/4 通过。
3. 另起错误 Key 的服务验证失败回退：HTTP 401 → 页面「本地规则 / 云端返回接口错误」，请求编号可追踪。
4. 采集 24 个固定样本 × 3 级 = 72 次真实调用：命中 67、回退 5、错误 0；云端中位 9.765 秒、P95 28.777 秒、最大 36.586 秒。5 次回退均为 `workflow_failed` / `AgentArts.102056`，失败节点为诊断或教学提示，回退路径按设计生效。
5. 按评分规则做助手初筛：云端 `evidence_ok 46/67`、`actionable 51/67`、`answer_leaked 0/67`；本地 72 条沿用已复核基线 `72/72、72/72、0/72`。初筛不是队员人工复核签字。
6. 质量结论：平均值题的符号、零除、数值范围样本一致性较好；分子少 1、分母数量偏差和总和/计数的硬编码样本常得到泛化提示（如把硬编码样本说成循环累加问题），是工作流提示词下一轮的主要改进点。
7. 报告：`evals/paired-results.json`、`evals/agentarts-acceptance-20261110.json`、`evals/agentarts-web-20261110.json`，复核表 `evals/agentarts-review.csv`。

仍未验收：队员逐条签字；`AgentArts.102056` 根因；其余 5 道教学题接入云端；真实服务器部署。
本机采集时用 `AI_TIMEOUT=60`、`AI_HINT_PROTECTION=0`；产品默认仍为 8 秒与保护开启。
