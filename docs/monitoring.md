# 监控与费用告警（P1-3）

当前状态：缓存、限流、熔断、结构化日志与汇总脚本已实现并在本机测试通过；华为云账户级费用告警与真实运行趋势**尚未在真实服务器验证**。

## 已有保护

`AI_HINT_PROTECTION=1` 时（`tools/start.py` 默认开启），进程内 `hint_guard` 执行：

| 规则 | 行为 |
| --- | --- |
| 缓存 300 秒、最多 256 条 | 相同题目、证据、等级直接复用，日志记 `cache_hit` |
| 同一时刻最多 2 个云端请求 | 超出记 `busy` 并回退本地提示 |
| 60 秒内最多 6 次云端调用 | 超出记 `rate_limited` |
| 连续 3 次失败 | 熔断 30 秒，记 `circuit_open`，再做一次探针放行 |

验证实际启动时生效：

```bat
cd /d F:\GPT\华为ict
python -B -m unittest tests.test_startup -v
```

单元测试断言启动器默认设置 `AI_HINT_PROTECTION=1`，且非法值阻止启动。真实服务器上还应在 60 秒内连续点 7 次不同题目的提示，确认第 7 次页面显示“已达本轮云端调用限额，使用本地提示”，并在日志看到 `rate_limited`。这一步属于真实环境验证，目前**未执行**。

本机端到端实测（模拟运行时，2026-11-10）：启用保护并指向 `tools/mock_agentarts.py` 后，连续 6 次不同题目/等级的提示全部命中云端；第 7 次返回 `source=local`、`fallback_reason=rate_limited`；再次请求第 1 条返回 `cache_hit=true`。这证明保护在真实服务进程中生效，但模拟运行时不能代表真实云端的延迟与额度表现。

## 日志

在 `/etc/ict-trial/environment` 设置：

```
AI_LOG_FILE=/var/log/ict-trial/application.jsonl
```

日志为每行 JSON，单文件上限 1,000,000 字节、保留 3 个轮转文件。每次提示请求记：

```json
{"ts":"2026-11-10T12:00:00+00:00","request_id":"...","source":"agentarts","elapsed_ms":9765,"fallback_reason":null,"execution_id":"...","cloud_error_code":null,"failed_node_id":null}
```

不记录提示正文、学生代码、Authorization 或客户端 IP。

## 汇总脚本

```bat
cd /d F:\GPT\华为ict
python -B tools\monitor.py "C:\path\to\application.jsonl" --since-minutes 60 --budget-per-day 300 --json evals\monitor-20261110.json
```

输出：调用总数、云端/回退数与命中率、回退原因分布、全部与云端的 P50/P95/最大耗时、每日调用量。`--budget-per-day` 超出时退出码为 1，可挂到计划任务里作为成本闸门。

口径说明：

- 回退率不是错误率。`not_configured`、`local_exercise`、`rate_limited`、`circuit_open` 是设计内降级；`timeout`、`connection_error`、`http_error`、`workflow_failed`、`invalid_output` 需要排查。
- 耗时看 P95 和最大值，不看单次。2026-11-10 真实采集的云端样本为 P50 9.765 秒、P95 28.777 秒、最大 36.586 秒；此前一次 7.7 秒不能代表稳定响应速度。
- 日志轮转后脚本只统计当前文件，历史趋势需要另行归档。

## 华为云费用告警（需账号管理员操作）

1. 费用中心 → 总览 → 可用额度/预算，设置预算与阈值（例如月度预算的 50%、80%、100%）。
2. 费用中心 → 消息接收人/通知管理，确认短信、邮件、站内信接收人。
3. 为 AgentArts 运行时与 MaaS 模型分别开启用量告警；按模型维度设置每日 Token 或调用量阈值。
4. 在 CES 为 ECS 设置 CPU、内存、磁盘与网络告警；磁盘剩余低于 20% 时告警。
5. 告警接收人必须包含值班队员；每月核对一次实际账单与预算。

这些步骤无法由仓库代码完成，也无法由助手代操作账号；完成后把截图或告警规则编号写入交付材料。

## 故障监测建议阈值

| 指标 | 建议阈值 | 动作 |
| --- | --- | --- |
| 回退率（排除设计内降级） | 5 分钟 > 10% | 查 `fallback_reason` 与 `execution_id` |
| 云端 P95 耗时 | 连续 10 分钟 > 30 秒 | 检查模型额度、节点耗时，必要时降级 |
| `workflow_failed` | 任意 1 次 | 控制台按 execution_id 查节点错误 |
| 每日云端调用 | 超过预算 80% | 通知值班队员 |
| 磁盘剩余 | < 20% | 清理日志或扩容 |

## 尚未完成

- 真实服务器上验证保护生效（第 7 次限流、熔断恢复）。
- 华为云费用告警与 CES 告警规则尚未创建。
- 连续多日真实运行的失败率与耗时趋势尚无数据；现有 72 次采集是一次性验收样本。