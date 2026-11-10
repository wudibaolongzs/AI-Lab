# 真实服务器部署验收（P1-1）

本文区分四层状态，当前只到第三层之前：

| 项目 | 代码/模板 | 本机验证 | 真实服务器验证 |
| --- | --- | --- | --- |
| nginx TLS、Basic 认证、Host 固定 | 已实现 `deploy/nginx.conf` | 静态检查与入口模拟通过 | **未验收** |
| systemd 服务与重启 | 已实现 `deploy/ict-trial.service` | 单元测试通过 | **未验收** |
| 部署黑盒检查脚本 | 已实现 `tools/verify_deployment.py` | 本机 HTTP 模拟 4 项测试通过 | **未验收** |
| 课堂/题库数据库备份恢复 | 文档步骤已写 | `verify_classroom.py` 验证重启持久化 | **未验收** |

部署 AgentArts 工作流不等于部署本项目的网页；两者的配置入口、验收证据和失败表现都不同。

## 前提

- 一台专用 Linux 主机、域名、已签发证书、nginx 与 `htpasswd`。
- 不在共享主机、也不在仓库目录内放密钥、数据库或证书私钥。
- 先按 [受控小规模试用部署](operations.md) 完成用户、目录、环境文件、systemd 与 nginx 配置。

## 一、启动与重启

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ict-trial
sudo systemctl status ict-trial --no-pager
curl -s http://127.0.0.1:8000/healthz          # 期望 {"status":"ok"}
sudo nginx -t && sudo systemctl reload nginx
```

重启验收（重启后仍能提供页面，课堂记录不丢）：

```bash
sudo systemctl restart ict-trial
sleep 2
sudo systemctl is-active ict-trial            # 期望 active
curl -s http://127.0.0.1:8000/healthz         # 期望 {"status":"ok"}
journalctl -u ict-trial -n 20 --no-pager      # 不应出现启动异常
```

## 二、外网入口黑盒检查

在能访问该域名的机器上执行（PowerShell 或 bash 均可；密码只放环境变量）：

```powershell
$env:DEPLOY_BASIC_PASSWORD = Read-Host '试用账户密码' -AsSecureString | ForEach-Object { [System.Net.NetworkCredential]::new('', $_).Password }
python -B tools\verify_deployment.py --url https://trial.example.com --basic-user trial01 --json evals\deployment-acceptance-20261110.json
```

```bash
export DEPLOY_BASIC_PASSWORD='从密码管理器读取，不要写进历史'
python -B tools/verify_deployment.py --url https://trial.example.com --basic-user trial01 --json evals/deployment-acceptance-$(date +%F).json
```

脚本逐项输出 PASS/FAIL，退出码 0 才表示入口验收通过。检查项：

1. 证书主机名与有效期（剩余少于 14 天给 WARN）。
2. HTTP 访问 301/302/307/308 跳到 HTTPS。
3. 未登录访问 `/`、`/api/exercises`、`/api/check`、`/api/hint` 均返回 401。
4. 伪造 `X-Forwarded-User`、`X-Remote-User`、`X-Forwarded-Authorization` 仍返回 401。
5. `/healthz` 经公网返回 403，仅本机可访问。
6. 登录后首页含“智学工坊”，`/api/exercises` 返回非空题目列表。

脚本不检查 `systemctl` 状态、防火墙、数据库文件和 nginx 配置语法；这些必须按下面的记录表人工核对。

## 三、数据库恢复演练

涉及三个 SQLite 文件，路径由环境变量决定，默认值如下：

| 数据 | 环境变量 | 默认路径 |
| --- | --- | --- |
| 课堂任务与求助 | `AI_CLASSROOM_DB` | 由操作员指定，例如 `/var/lib/ict-trial/classroom.sqlite` |
| 题库 | `AI_QUESTIONBANK_DB` | `data/question-bank.sqlite3` |
| 洛谷远程任务 | `LUOGU_DB` | `data/remote.sqlite3` |

备份（服务可在线执行，SQLite backup API 保证一致性）：

```bash
mkdir -p /var/lib/ict-trial/backup
python3 - <<'PY'
import os, sqlite3, time
pairs = [("小学/课堂", os.environ.get("AI_CLASSROOM_DB")),
         ("题库", os.environ.get("AI_QUESTIONBANK_DB")),
         ("洛谷", os.environ.get("LUOGU_DB"))]
for label, source in pairs:
    if not source or not os.path.exists(source):
        print(label, "未启用，跳过")
        continue
    target = f"/var/lib/ict-trial/backup/{os.path.basename(source)}.{time.strftime('%Y%m%d-%H%M%S')}"
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    print(label, "已备份到", target)
PY
```

恢复演练（在试用前做，不要在真实课堂进行中做）：

```bash
sudo systemctl stop ict-trial
cp /var/lib/ict-trial/backup/classroom.sqlite.<时间戳> "$AI_CLASSROOM_DB"   # 按实际变量替换
sudo systemctl start ict-trial
curl -s http://127.0.0.1:8000/healthz
```

恢复后用教师凭证访问 `/api/classroom/teacher`，核对任务数、求助数与恢复前一致；再让学生凭证读取本人求助，确认回复仍在。题库与洛谷数据库同理，恢复后各取一道题做一次判题。

## 四、验收记录

复制下表到交付材料，逐项填“通过/失败/未做”并附命令输出或截图摘要：

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 证书主机名正确、剩余 > 14 天 | | 脚本输出 |
| HTTP 跳转 HTTPS | | 脚本输出 |
| 未登录四类请求均 401 | | 脚本输出 |
| 伪造身份头仍 401 | | 脚本输出 |
| 公网 `/healthz` 403 | | 脚本输出 |
| 登录后首页与题库可用 | | 脚本输出 |
| `systemctl restart` 后 active | | `systemctl is-active` |
| 重启后健康检查 200 | | `curl` |
| 课堂数据库备份与恢复 | | 备份文件名 + 教师端记录数 |
| 题库/洛谷数据库恢复后判题正常 | | 判题响应 |
| 防火墙仅开放 443（80 仅跳转） | | `ss -lntp` / 安全组截图 |

全部通过才可对外宣称“真实服务器已验收”。只跑 `tools/verify_deployment.py` 通过，不等于重启和数据库恢复也已验收。