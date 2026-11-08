# 学习闭环使用说明

更新：2026-11-08。

## 本次完成
- 题库8道：平均值、总和、计数、双倍总和、整体平移后的平均值、含一次固定费用的总额、每件两张标签计数、追加零后的平均值。支持范围仍是受限AST，不执行任意Python。
- 原题通过后显示固定数值变式；可选填写自述解释，自述保存于本机但不评分，不据此宣称掌握。
- 记录变式验证次数、首次是否正确，编辑、重跑或切题取消旧响应。
- 提示有四类反馈，保存在当前浏览器；JSON导出只包含练习记录，导入先完整校验，覆盖同题前有界面说明，写入失败尝试回滚。
- 可选课堂工作台：独立师生凭据、班级隔离、SQLite任务/求助/回复。学生求助是自述，不是模型执行证明。

## 立即运行
在根目录运行 python -B tools/start.py --port 8001，打开终端地址。平均值题运行预置错误，领取提示，改正分母到len(nums)，4/4通过后填写解释和变式答案。
可尝试先答错再答对，观察独立验证状态；原题通过和变式正确分别记录。
历史记录附近可导入导出当前浏览器数据；导出文件可能含草稿和自述，请自行决定是否分享。

## 课堂工作台
练习页顶部“课堂工作台”进入 /teacher。默认未配置时不可登录，这是预期。
按 [课堂配置](classroom.md) 在仓库外生成真实凭据和数据库路径，再在本机.env或环境设置AI_CLASSROOM_CONFIG、AI_CLASSROOM_DB，重启。
每人只领取自己的凭据；教师发布任务、学生填问题、教师回复。页面凭据只在内存，刷新或退出清除。
浏览器使用X-Classroom-Token与网关Basic登录分离；公网仍需现有HTTPS、鉴权、防火墙和部署验收。
这不是跨设备同步全部练习草稿的账户系统，也不是生产级教务平台。

## 接口
- GET /api/learning/challenge?exercise_id=average：题目和question_id，不含标准答案。
- POST /api/learning/verify：exercise_id、code、有限数值answer、可选explanation（最多500字）。服务端复验原题通过，不通过409；验证答案独立判断。
- /api/classroom/*：角色、权限、配置和数据库见课堂文档。
- /api/check与/api/hint保持旧用法。

## 评测范围
原evals/samples.json仍为24个样本/72个提示位置，不改历史报告。
新增evals/curriculum-samples.json为15个新题错误样本/45个提示位置。独立复现：
python -B -m evals.run --samples evals/curriculum-samples.json --output evals/curriculum-rerun.json
本地自动采集不等于人工质量复核。新题默认只走本地提示；工作流适配、独立评测完成后再显式加入AGENTARTS_EXERCISES。

## 验证结果
本轮154项Python测试全部通过；16项本机Edge浏览器测试通过。云服务使用缺配置本地回退或测试替身，没有新增真实付费调用。
浏览器测试命令：PowerShell设置 $env:PLAYWRIGHT_CHANNEL='msedge' 后运行 npm run test:browser。

## 仍需实际完成
1. 队员复核已有144个提示位置，不能自动填满或把AI审阅称为人工评分。
2. 华为工作流配置到位后单独采集真实报告并关联执行记录。
3. 参考 [试用方案](pilot/README.md) 招募自愿学生，记录实际结果；目前无教学效果结论。
4. 服务器上的证书、网关、身份撤销、备份恢复和外部访问验收。
