# 统一题库与维护者导入

## 当前版本
默认提供28题：原8题迁移为data/builtin.json，新20题位于data/exercism-foundations.json。
原8题题号、旧判题路径、提示措辞与变式答案保持兼容。新增题使用受限解释器。
题库不是在线抓取，运行时不依赖Exercism；固定来源修订与MIT说明见 [开源来源](open-source-bank.md)。

另有300道资料练习题（data/local-reference-bank.json，150对，Python/C++各150），与上述28题合并为628题的浏览目录。资料题只有题面、函数签名、起始代码和三级提示，`capabilities` 全部为 false：不提供在线判题、提示请求和变式验证。来源字段统一为「本地导入题库」，仓库内没有单独的授权清单，对外发布前需维护者确认授权与收录范围。

## 分发授权确认

提交 `data/local-reference-bank.json` 前需维护者确认，未确认时不要把它当作可公开交付内容：

1. 300 道题的题面、起始代码和提示是否允许公开再分发（仓库、演示、评审材料）。
2. 是否允许与洛谷目录、Exercism 题目同目录展示。
3. 是否允许队友通过 Git 拉取后直接运行。

若只能本地使用，把数据文件放在仓库外，启动前设置 `AI_REFERENCE_BANK` 指向该文件；未设置且仓库内文件缺失时，资料题自动为空，服务仍可启动。已验证仅含 Git 跟踪文件的副本运行时目录为 328 题、资料题 0 题、知识点 109 个，对应测试会失败——这正说明提交数据文件是交付的一部分。

## 使用
正常运行 python -B tools/start.py --port 8001。页面上方题库支持关键词、知识点、难度、来源、编程语言和分页；下拉选项由 `/api/catalog/options` 从统一目录生成，包含资料题独有的知识点（例如「二进制」「前缀」）。练习模式可选全部、本地练习、洛谷远程判题和资料练习。下拉框保留快速切题。题目详情显示来源许可。
新题没有变式时显示“暂未配置理解验证”，不显示已掌握。编辑器支持范围随执行方式显示。资料题只提供“查看题目”和“查看提示”，并明确提示暂不支持在线判题。

## 命令行导入
在项目根目录执行：
```powershell
python -B tools/question_bank.py validate data/example-import.json
python -B tools/question_bank.py preview data/example-import.json
python -B tools/question_bank.py --db data/question-bank.sqlite3 import data/example-import.json
```
第三条命令将额外发布示例题；它不在默认28题中。服务默认读取该数据库，刷新网页重新加载目录即可看见。
如设置AI_QUESTIONBANK_DB，导入命令和服务必须使用同一个数据库绝对路径；课堂数据库保持独立。
默认28题已随源码发布，不需要重新导入exercism-foundations包；对它运行validate/preview可以核查，但import会报告题号冲突，这是预期。
导入是本机维护操作，不开放网页上传；参考解和测试不进入公共题目接口。

## 题包约定
schema_version固定为1，pack_id与version必填，problems最多200题，文件最多2MiB。
完整可复制示例见data/example-import.json。每题需要稳定id和version、题面、知识点、难度、学习目标、来源与许可证、函数签名、参数与返回类型、初始错误代码、参考解、最多32个测试用例和3条提示。transfer是可选的固定数值变式。
支持参数类型number、integer、boolean、string、number_list；返回值同样按声明类型校验。
外部题只能使用bounded_v1；legacy仅供内置旧题。参考解需全部通过，起始代码必须产生有效失败。不能在题包中导入新的执行插件。
同包重复题号、与内置或已导入题冲突均拒绝；整包事务发布，失败不覆盖既有题。不支持更新和撤回功能，需另行设计版本迁移。
发布后若重做题目或测试，不应私自复用旧题号以免学习记录失真。

## 执行边界
白名单支持基础数值、布尔、字符串、比较、逻辑短路、if/elif/else、条件表达式、取模/整除、受限索引/切片和sum/len/abs/int/str。
继续拒绝循环、递归、导入、属性调用、自定义函数调用、幂运算和任意Python执行。源码4000字符、AST160节点、深度16、执行1000步、数值绝对值不超过10的12次方；字符串及序列另有限额。
这是教学解释器，不是完整Python沙箱；需要循环等能力时应接独立隔离执行服务。

## API
- GET /api/exercises：保留数组接口，返回公开元数据。
- GET /api/catalog/options：返回统一目录的知识点、来源和语言选项，不受当前筛选与分页影响。
- GET /api/catalog?query=&tag=&difficulty=&source=&language=&mode=all&page=1&page_size=12：分页，page_size范围1–100；mode取all、local、remote、reference；language取python或cpp。
- GET /api/problems/题号：公开详情。参考解、测试和变式答案不返回；资料题按 bank- 前缀查询。
- /api/check与/api/hint保持既有响应结构；新题默认本地提示，云端需另行适配和验收。
- 题包答案是服务端材料；判题完成后仍按原练习产品规则展示用例反馈，不作为隐藏试题考试系统。

## 评测与验证
原24样本/72提示位置不变。新题evals/bank-samples.json有20样本，独立采集：
```powershell
python -B -m evals.run --samples evals/bank-samples.json --output evals/bank-local-rerun.json
```
本轮173项完整Python测试及18项本机Edge浏览器测试通过，干净副本173项也通过。没有付费模型调用。
参考实现与期望值按教学规则核对，自动通过只证明当前固定用例，不证明题目毫无遗漏；新增本地报告未自动填写人工质量评分。

## 后续入口
下一阶段才接洛谷授权评测；远程提交源码前明确告知用户。百度OCR录题助手现已提供：见 [录题指南](baidu-materials.md)。识别结果进入私有草稿，经校验和人工审核导出后，由维护者发布。
