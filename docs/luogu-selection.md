# 洛谷目录范围与来源

当前发布的是 300 题的**元数据目录**，分成 3 个各 100 题的 schema_version 2 remote 包。原有 28 道本地题保持独立，另有 300 道资料练习题（150 对，Python/C++ 各 150），总目录为 628 道。洛谷条目展示“题面待授权同步”，通过官方链接阅读；不提供本地判题、提示或迁移题。资料题只展示题面、起始代码和提示，也不提供在线判题。

官方文档：https://docs.lgapi.cn/open/judge/ 。该页明确列出官方导出 https://cdn.luogu.com.cn/problemset-open/latest.ndjson.gz 。2026-11-08 读取，gzip SHA256、压缩/解压大小、记录数、原始字段、每题分类依据和冻结 PID 详见 `data/luogu/selection-manifest.json`。请求不使用 Cookie、平台账号或非官方抓取。读取上限为压缩 64 MiB、解压 256 MiB、单行 2 MiB。

按官方标签匹配主分类，优先难度 1、其次 2；同难度优先 B2 入门系列、深基系列，再按数字 PID 排序，在分类配额顺序中去重选取。配额：输入输出 30、条件分支 30、循环 40、数组 50、字符串 40、排序与查找 35、模拟与数学 35、搜索 20、贪心 20。筛除标注交互、提交答案、远程、通信类题目及缺少输入格式、输出格式或样例的记录。该筛选依赖官方导出标签，未逐题试交；教师应在安排作业前复核官方题面。

官方导出不含逐题语言列表，因此 Python / C++17 是应用配置的提交语言候选，不能据此声称全部 300 题已经 Python 验证。难度 1 映射 easy、2 映射 medium，原始难度及标签保留于 remote 字段。

题面、背景、输入输出说明、样例、翻译、解答和测试数据均未进入公开包；来源 license 显示“授权待确认”。开放导出可下载不等同于完整题面再分发授权。获得明确内容授权后才可设置 `LUOGU_CONTENT_AUTHORIZED=1`，通过专用导入器导入含内容的扩展包。此环境变量是操作者的明确授权声明，不是平台凭据，也不证明任何许可。

元数据校验/预览无需平台凭据：

```powershell
python tools/luogu_bank.py validate data/luogu/pack-1.json
python tools/luogu_bank.py preview data/luogu/pack-1.json
python tools/luogu_bank.py import path/to/new-remote-pack.json --db data/question-bank.sqlite3
```

普通 v1 本地包导入器拒绝 remote 包；专用导入器限制 2 MiB 和 200 题，拒绝重复 ID 并以数据库事务写入。内置 ID 不允许被导入覆盖。浏览目录与远程提交权限独立，提交是否可用由服务端平台配置与授权决定。
