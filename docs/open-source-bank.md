# 开源基础题库来源与改编

题包 `exercism-foundations` 版本 `1.0.0` 含20道中文单函数题。来源是 [Exercism Python](https://github.com/exercism/python)，固定修订为 `479f11b44b02337b0413e805b948491c2179615a`。这是获取时 GitHub commits/main API 返回的提交，不在运行时访问网络或跟踪分支变化。

|上游练习目录|本地拆分数|范围|
|---|---:|---|
|concept/guidos-gorgeous-lasagna|3|剩余、准备、总时间|
|concept/ghost-gobble-arcade-game|4|eat_ghost、score、lose、win|
|concept/meltdown-mitigation|3|临界状态、效率、保护状态|
|concept/black-jack|5|单牌、A、Blackjack、分牌、加倍；不含返回元组的higher_card|
|concept/little-sisters-vocab|1|add_prefix_un|
|practice/leap|1|闰年|
|practice/triangle|1|正边长等边三角形|
|practice/darts|1|飞镖得分，本地函数名score_dart|
|practice/reverse-string|1|字符串反转|

`third_party/exercism/upstream/` 保存上述固定修订的 `.meta/config.json`、题目说明、起始文件、测试与示例实现。实际文件名从各题 config 的 files 读取；没有执行上游代码。`upstream/LICENSE` 保留完整 MIT 许可及 `Copyright (c) 2021 Exercism`。本题包每题记录固定提交的原始目录链接、许可、署名和改编说明。分发本题包时须一并保留该许可和署名。

改编包括中文重述、将组合任务拆为独立题、限定合法输入、重写错误起始代码、独立参考实现、本地边界用例和三级概念提示。三角形只保留等边判定；所有返回值均为标量；参考实现不依赖辅助函数、导入、循环或上游运行环境。教学核反应堆题只是原题数值规则练习。

本地期望值最初由本地编写的参考表达式计算，再按题目规则逐项人工复核，并非原样导入上游测试。生成器已移除，上游源码从未执行。应用只加载JSON并在受限AST解释器中运行学生代码。`evals/bank-samples.json` 新增20个错误样例，保留既有24个回归样例与报告。

验证：`python tools/question_bank.py validate data/exercism-foundations.json` 和 `python -m unittest discover -s tests -p test_bank_content.py`。后者检查20题、分组数、许可固定修订、所有参考用例通过、所有起始代码失败以及评测样例首个失败位置，不需要联网。

人工复核覆盖：40减烘烤分钟、每层2分钟及总和；全部双布尔和获胜状态；800/500/500000严格比较；效率80/60/30档位；阈值90%与110%两端点；A、人头牌、分牌、9/10/11加倍；前缀与逆序；1900与2000闰年差异；零与负边长；飞镖半径1/5/10内圈边界。参考通过本地用例本身不能作为独立正确性证明。
