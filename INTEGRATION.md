# AI-Lab 整合交接记录

本文为整合当天的历史验收快照。之后的启动配置和测试入口见 [部署与协作说明](docs/local-deployment.md)，云端联调状态需以实际请求和控制台执行记录复核。

2026-11-07 合入队友提供的 AI-Lab.zip。保留平均值网页云端入口，后端多题开关供模拟联调使用。

## 验证结果

- 88 项自动化测试通过，浏览器完成三级本地提示、平均值修正后 4/4、切题和刷新草稿恢复。
- `python -B tools/verify_agentarts.py` 的 8 组检查通过，包括正常模拟、异常回退、超时及默认平均值范围。修正了 Python 3.9 的 socket.timeout 分类。
- `evals/local-baseline.json` 是本次重新采集的 24 样本、72 条本地提示。逐条文本与队友基准相同，人工评分沿用队友记录，评分器完整性检查通过。
- `evals/local-fallback.json` 是本次 72 次本地接口回退采集，错误 0 次。
- `evals/mock-paired-results.json` 是本次模拟配对采集，72 个位置走通模拟工作流，日志关联检查通过。模拟提示的人工质量评分留空，不能作为真实云端教学质量结论。
- 合并前报告保存在 `evals/history/local-before-merge/`，队友历史报告保存在 `evals/history/teammate/`。`average_failures.json` 保留原 12 条平均值样本，评测脚本现使用 `samples.json` 的 24 条统一样本。

## 队友接手顺序

1. 解压进入 AI-Lab，运行 `python -B -m unittest discover -s tests -q`，再运行 `python -B app.py`，使用终端显示的地址。
2. 运行 `python -B tools/verify_agentarts.py` 检查本机模拟链路。
3. 按 README 发布真实工作流，在自己的终端配置调用地址和运行时 Key。用 `tools/probe_agentarts.py` 检查真实调用，再按 README 采集和人工评分。
4. 使用 `python -B -m evals.score evals/local-baseline.json --require-complete` 核对本地基准。新真实配对报告需按评分说明逐条复核后再使用 `--require-complete`。

2026-11-10 真实云端验收已通过三道题三级提示与 72 次配对采集（命中 67、回退 5、错误 0）；云端提示质量的人工复核签字与异地部署仍未完成。服务默认监听本机地址，手机和异地访问需要另行部署。
