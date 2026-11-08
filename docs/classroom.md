# 本地课堂工作台（可选）

默认关闭。仅在原有 localhost 服务中提供 `/teacher` 页面和 `/api/classroom/*` API；不是公网身份系统。教师和学生凭证各自独立，服务器从凭证确定班级、角色和学生身份，忽略客户端学生身份字段。

## 操作员配置

在仓库外准备一个仅当前操作员可访问的目录，例如 `C:\Users\你的账户\private-classroom`。以下命令由操作员主动执行，生成全新随机凭证；不会覆盖已有文件，也不会在终端打印凭证：

```powershell
python tools/classroom_config.py --output C:\Users\你的账户\private-classroom\credentials.json --class-id class-a --students student-01 student-02
$env:AI_CLASSROOM_CONFIG = 'C:\Users\你的账户\private-classroom\credentials.json'
$env:AI_CLASSROOM_DB = 'C:\Users\你的账户\private-classroom\classroom.sqlite'
python app.py
```

Windows 下请使用文件属性或 ACL 将该目录权限限制到操作员账户；`0600` 文件模式不替代 Windows ACL。只向每位学生单独分发其本人的凭证；教师凭证只给本班教师。不要提交配置、数据库或凭证到版本库。首次启用前数据库目录必须存在。数据库含求助文本、学生别名及教师回复，应按课堂记录管理；停用并删除数据库可清除记录。

JSON 结构为 `{"classes":{"班级ID":{"teacher_token":"操作员生成的随机凭证","students":{"学生别名":"该学生独有随机凭证"}}}}`。所有凭证必须唯一、至少 24 个 ASCII 字符且不包含空白。可手动扩展多个班级。关闭服务后轮换配置中的相应凭证并重启即可撤销旧凭证。配置无效、缺少环境变量或无法读取配置时 API 返回 503。

## 接口

页面请求使用独立的 `X-Classroom-Token: <专属凭证>`，避免与网关Basic认证冲突。本机脚本也兼容 `Authorization: Bearer <专属凭证>`，禁止在 URL 中传凭证。无效凭证返回 401，角色不符返回 403；跨班级回复返回 404。凭证不出现在 JSON 响应中。页面只将输入凭证保留在内存，刷新或退出清除，不写入浏览器存储。

- `GET /api/classroom/student`：本人班级的 `tasks`、仅本人 `help`（含教师回复）、`class_id`。
- `POST /api/classroom/help`：`exercise_id` 必须属于当前练习集；`submission_id`、`request_id` 必填且不超过 100 字符；`question` 必填且不超过 1000 字符；`hint` 可选且不超过 240 字符；`source` 仅支持 `local/ai/agentarts/deepseek/tencent/fallback/manual` 等来源标记，不接收代码。返回记录 `id`。同一学生相同 `request_id` 幂等，不覆盖已有记录。
- `GET /api/classroom/teacher`：本班 `tasks`、本班求助 `help` 和 `counts`（任务数、求助数、待回复数），不推断学习效果或正确率。
- `POST /api/classroom/tasks`：`exercise_id`、`title`（1–160 字符）、可选 `due`（最多 80 字符的展示文本）。返回任务 `id`。
- `POST /api/classroom/reply`：`help_id` 和 `reply`（1–1000 字符）。仅能回复本班记录；可修改已有回复。

任务和求助存 SQLite，服务重启后保留；仅记录求助元数据和明确提交的问题/提示，不采集原始学生代码，不创建学习分析。`/teacher` 支持教师发布/回复和学生查看本人求助。学生从练习页“课堂工作台”链接进入 /teacher，选择学生身份后填写求助表单。来源固定为manual，属于学生主动自述，不是服务端验证的判题或云端执行证明。

验证：`python -m unittest discover -s tests -p test_classroom.py -v`，覆盖禁用、无效凭证、角色隔离、班级及学生隔离、持久记录、幂等、长度和来源校验。


教师资料与拍照录题已提供独立待审核草稿区，仍使用本文件的教师凭证与课堂数据库。配置百度OCR、支持格式与审核导出流程见 [录题指南](baidu-materials.md)。
