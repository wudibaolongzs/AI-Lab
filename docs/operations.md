# 受控小规模试用部署

这是基于 Python 标准库 HTTP 服务的原型模板，适用于受控小规模试用；不承诺生产规模可用性。模板与静态测试已实现，**尚未在真实服务器验收**；部署验收记录见 [真实服务器部署验收](deployment-acceptance.md)。每个进程最多接受 16 个并发连接，超出立即返回 503。代理鉴权只提供试用入口保护，不提供账户、会话撤销或租户隔离。

## Linux 管理员操作

1. 准备专用 Linux 主机、Python 3、nginx 与域名。由管理员配置 DNS 和合法 TLS 证书。将 `deploy/nginx.conf` 中所有 `example.invalid` 和证书路径替换为实际值；示例不会申请证书。
2. 创建无登录 shell 的 `ict-trial` 用户与组。将代码放在 `/opt/ict-trial`，由管理员拥有、服务用户只读。创建 `/var/lib/ict-trial`、`/var/log/ict-trial`，服务用户可写。应用运行目录与密钥目录不得作为静态站点根目录。
3. 在仓库外创建 `/etc/ict-trial/environment`，权限 0600、root 拥有。服务单元默认设置 AI_HINT_PROTECTION=1；不要在共享环境关闭它。将需要的 AI 配置放入此文件（systemd 环境文件格式，不要 `export`），例如 `AI_LOG_FILE=/var/log/ict-trial/application.jsonl`。不要把真实密钥复制进仓库。日志可选；启用后单文件最多 1,000,000 字节并保留 3 个轮转文件。日志父目录须预先创建。
4. 用 `htpasswd` 在 `/etc/ict-trial/htpasswd` 创建独立试用账户，交互输入强密码。仅 root 与 nginx 工作进程组可读。TLS 与 basic_auth 同时启用；账户名单撤销通过更新该文件完成。
5. 安装 `deploy/ict-trial.service` 到 systemd 单元目录；检查解释器路径。安装 nginx 配置到其 http 上下文，关闭默认虚拟主机，确保无其他配置绕过认证。运行 `nginx -t`、`systemd-analyze verify`，然后由管理员启用服务并重载 nginx。
6. 防火墙只向外开放 443（80 仅供跳转或证书流程）。应用固定监听 `127.0.0.1:8000`，禁止公开映射 8000。所有共享环境本地用户都可直连该端口，因此仅在可信专用主机部署。nginx 将上游 Host 固定为 `127.0.0.1:8000`；应用不信任客户端转发的身份头，模板还会清除这些头。

## 上线前验证

- 本地 `curl http://127.0.0.1:8000/healthz` 应仅返回 `{"status":"ok"}`，不触发云服务。
- 从外部不带认证访问 `/`、`/api/exercises`、`/api/check`、`/api/hint` 均应返回 401；即使伪造转发身份头也如此。使用有效账户经 HTTPS 检查正常流程。
- `/healthz` 经公网代理返回 403；本机监控可直连应用。Host 不在白名单时返回 400。
- JSON 请求访问日志仅记录固定路由名、受限方法名及状态码；不记录 URL 查询、提交代码、Authorization 或客户端 IP。nginx 访问日志关闭、错误日志仅记录 crit。操作系统、上游供应商与其他代理日志需按自身配置审查。
- `journalctl -u ict-trial` 查看运行状态。停止试用时停止服务和代理入口、撤销试用密码、轮换提供商密钥。运行日志是否留存由管理员制定，切勿向日志添加请求体或令牌。

修改应用之后重启 systemd 服务；修改 nginx 配置前先运行 `nginx -t`。这些检查是部署验收步骤，仓库静态测试不能证明真实网络、证书和防火墙状态。
启用 nginx 后用黑盒脚本检查一次入口（密码只放环境变量）：

```bash
export DEPLOY_BASIC_PASSWORD='从密码管理器读取'
python -B tools/verify_deployment.py --url https://trial.example.invalid --basic-user trial01
```

服务重启、数据库备份恢复与完整验收记录见 [真实服务器部署验收](deployment-acceptance.md)。监控和费用告警见 [监控与费用告警](monitoring.md)。
