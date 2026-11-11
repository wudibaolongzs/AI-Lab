# 2026-11-11 模拟验收记录

本页全部是**本机模拟**，用于把可自动化的检查先跑通，不替代真实服务器、真机、真人与第三方授权验收。引用状态时仍按四级口径：代码已实现、模拟通过、真实通过、尚未验收。

## P0 提示复核（模拟初筛）

- 复核表：[after-20261111-review.csv](../evals/after-20261111-review.csv)，143 行；本地 72 条复用 `local-baseline.json` 的已复核分，云端 71 条由助手按评分规则做**规则初筛**。
- 报告：[paired-results-after-20261111-ai-reviewed.json](../evals/paired-results-after-20261111-ai-reviewed.json)。
- `evals.score --against evals/local-baseline.json --require-complete` 退出码 0，待复核 0：
  - 本地 72/72、72/72、0/72；
  - 云端 `evidence_ok 49/71`、`actionable 55/71`、`answer_leaked 0/71`。
- 对比：[prompt-revision-compare-ai.json](../evals/prompt-revision-compare-ai.json)：
  - `evidence_ok` 修复 14、回归 13、仍失败 7、通过 32；
  - `actionable` 修复 14、回归 13、仍失败 2、通过 37；
  - `answer_leaked` 无泄露（66 条共同位置全部通过）。
- 结论：**模拟初筛不显示提示质量改善**，修复数与回归数接近；回归项可能是规则误判，必须由队员逐条复核。不得把 49/71 当作人工签字。

## P1 云端等待、限流与监控（模拟）

- [wait-experience-simulated.json](../evals/wait-experience-simulated.json)：开启 `AI_HINT_PROTECTION=1`（60 秒窗口 6 次、并发 2），连续 8 个位置 → 6 次云端、2 次 `rate_limited` 回退；前端文案为「已达本轮云端调用限额，使用本地提示」。耗时来自 1 秒 mock，不代表真实云端。
- 真实云端基线仍取有效版报告：71 次中位 6.92 秒、P95 26.68 秒、最长 55.12 秒；最长值距 60 秒 `AI_TIMEOUT` 余量偏小。
- [monitor-simulated.json](../evals/monitor-simulated.json)：72 行日志汇总，云端 71、回退 1、命中率 0.986；`--budget-per-day 60` 触发预算告警（退出码 1），`80` 通过。
- 仍缺：真实试用会话的日志、华为云账户费用告警与 CES 故障告警（需账号管理员）。

## P1 部署、课堂、手机与数据库恢复（模拟）

- [deployment-acceptance-simulated.json](../evals/deployment-acceptance-simulated.json)：本机 Python 代理模拟 nginx Basic Auth、healthz 拒绝、伪造头过滤和转发；8 项 PASS，TLS 与 HTTP 跳转 SKIP。**没有验证真实证书、DNS、主机防火墙与重启。**
- [classroom-acceptance-simulated.json](../evals/classroom-acceptance-simulated.json)：临时教师/学生凭证走通发布、求助、幂等、跨班隔离、教师回复、重启持久化，13 项 PASS。
- 移动端：`tests/browser/mobile.spec.js` 5 条 Playwright 视口测试通过（390×844 与更矮视口）；**不是 iPhone/安卓真机**。
- [db-restore-simulated.json](../evals/db-restore-simulated.json)：SQLite 备份、删除后确认空库、恢复后任务/求助/回复仍在，5 项 PASS。

## P2 洛谷与百度 OCR（模拟）

- `tests.test_luogu_bank`、`tests.test_remote_judge`、`tests.test_remote_http`、`tests.test_baidu_ocr` 共 26 项通过。
- 仍为：洛谷 **0 次真实试交**、百度 OCR **0 次真实识别**；授权到位后按 [外部服务验收](external-services-acceptance.md) 各做少量真实样本。

## 仍须真实环境完成

真实服务器 HTTPS 与证书、服务重启与数据库恢复、iPhone/安卓真机、教师+学生真人试用、华为云费用与故障告警、洛谷与百度 OCR 真实调用。