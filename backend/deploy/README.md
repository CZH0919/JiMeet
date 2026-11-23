# 后端运行手册

适用于 Linux 上的 Django 后端、PostgreSQL 15 及以上版本和同机 Nginx。浏览器访问同一个 HTTPS 域名，Nginx 提供前端静态文件并将 `/api/v1/` 原路径转发给 Gunicorn。后端仅监听 Unix 套接字。下文以 `jimeet.example.edu` 为示例，部署时替换为实际域名。

## 1. 配置与启动

1. 准备 PostgreSQL 数据库及具有该库迁移权限的应用角色。将[环境变量模板](../.env.example)复制到部署主机的 `/etc/jimeet/backend.env`，权限设为 0600。容器运行参数如下。

   | 参数 | 生产取值 |
   | --- | --- |
   | `DJANGO_SECRET_KEY`、`JIMEET_REGISTRATION_HMAC_KEY` | 分别生成并持久保管的随机密钥。前者建议至少 50 个字符，后者至少 32 个字符 |
   | `DJANGO_ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS` | 例如 `jimeet.example.edu`、`https://jimeet.example.edu`。首个允许主机填写实际域名，供容器探活使用 |
   | `ALLOW_DEV_LOGIN`、`DJANGO_DEBUG`、`JIMEET_TRUST_HTTPS_PROXY` | 分别设为 `false`、`false`、`1`。仅在使用下述受限套接字和覆盖转发头的代理时开启信任 |
   | `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD` | 实际数据库连接参数。示例使用 Linux 主机网络，可连接主机回环地址上的数据库 |
   | `PRIVATE_FILE_ROOT` | 容器内设为 `/var/lib/jimeet/private`，持久卷仅对应用账号开放 |
   | `JIMEET_SMTP_*` | 同济 SMTP 使用 465 端口、隐式 TLS，发件地址等于认证账号，密码使用客户端专用密码 |

2. 由部署管理员创建运行目录。镜像以 UID 10001 运行，套接字组填写实际 Nginx worker 组。私有简历目录与前端静态目录分开。

   ```sh
   install -d -o 10001 -g www-data -m 2750 /var/lib/jimeet/socket
   install -d -o 10001 -g 10001 -m 0700 /var/lib/jimeet/private
   ```

3. 从仓库根目录构建镜像。升级前备份数据库及同一恢复点的私有文件，暂停旧应用写入和定时任务。先运行迁移和标签初始化，再启动应用。同一套接字只允许一个服务实例绑定。

   ```sh
   IMAGE="jimeet-backend:$(git rev-parse --short HEAD)"
   docker build -t "$IMAGE" backend
   docker run --rm --network host --env-file /etc/jimeet/backend.env "$IMAGE" python manage.py migrate --noinput
   docker run --rm --network host --env-file /etc/jimeet/backend.env "$IMAGE" python manage.py seed_tags
   docker run -d --name jimeet-api --restart unless-stopped --network host \
     --env-file /etc/jimeet/backend.env \
     --mount type=bind,src=/var/lib/jimeet/socket,dst=/run/jimeet \
     --mount type=bind,src=/var/lib/jimeet/private,dst=/var/lib/jimeet/private \
     "$IMAGE"
   docker exec jimeet-api python manage.py migrate --check
   docker exec jimeet-api python deploy/healthcheck.py
   ```

   首次部署直接使用以上命令。升级时先停用并移走旧的同名容器，保留原镜像标签与备份。纯应用回退须确认旧版本兼容当前库；涉及不可逆清理时，按第 3 节在新库验证恢复点。

4. 将构建好的前端 `dist/` 内容发布至 `/srv/jimeet/frontend/`。按[代理配置示例](nginx.conf.example)替换域名与证书路径，完成 `nginx -t` 后重载。HTTP 跳转 HTTPS，Nginx 在 API 入口覆盖来源地址和协议，保留 Host 与 Cookie。Session Cookie 使用 Secure、HttpOnly、SameSite=Lax，CSRF Cookie 使用 Secure、SameSite=Lax。不要将私有文件挂入静态目录。

   公网探活使用 `GET /api/v1/healthz`。数据库查询成功返回 200 和 `data.status="ok"`，失败返回 503；SMTP 使用独立探测。部署后从真实域名核对证书、跳转、Cookie、代理日志及前端同源写请求。[Gunicorn 代理说明](https://gunicorn.org/deploy/)

## 2. 调度与告警

在一台调度主机配置[用户 crontab 示例](crontab.example)，按实际安装目录替换 `/opt/jimeet`。运行账号须能执行指定容器命令、读取自己的备份凭据及写入锁和备份目录。将示例五行加入该账号现有 crontab，沿用主机时区。无需在 Web worker 中另启任务。

| 任务 | 示例频率 | 成功与失败 |
| --- | --- | --- |
| `run_sync_recruitments` | 每分钟 | 处理截止、满员、七天到期。单项失败时继续处理其他招聘，最终返回非零 |
| `run_purge_applications` | 每小时第 8 分 | 满 180 天汇总申请并清理关联明细，重试简历删除；尚有文件待重试时返回非零 |
| `run_purge_chat_messages` | 每小时第 18 分 | 分批清理满六个自然月的消息。到期读取限制即时生效 |
| `check_registration_mail` | 每 10 分钟 | 检查 TLS、SMTP 登录及已完成投递的失败比例，不向用户发送探测邮件 |
| `backup` | 每天 02:35 | 创建并校验 PostgreSQL 自定义格式备份，再轮换超期副本 |

调度脚本读取 `/etc/jimeet/ops.env`。该文件为受信任的 Shell 配置，权限设为 0600，仅允许运维账号写入。预先为调度账号创建 0700 的备份与锁目录，准备 0600 的 PostgreSQL 密码文件。以下为配置示例。

```sh
JIMEET_CONTAINER=jimeet-api
JIMEET_LOCK_DIR=/var/lib/jimeet-ops/locks
JIMEET_BACKUP_DIR=/var/backups/jimeet
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=jimeet_backup
PGDATABASE=jimeet
PGPASSFILE=/etc/jimeet/backup.pgpass
# 填写独立告警系统的 curl 配置路径，可与主机日志告警配合使用。
JIMEET_ALERT_CURL_CONFIG=
```

任务由 `flock` 避免同类重叠。命令失败会向系统日志写入 `daemon.err`、标签 `jimeet-ops`，保留非零退出码；通过 `journalctl -t jimeet-ops` 查看。部署时将这一事件接入值班通知，或在 `JIMEET_ALERT_CURL_CONFIG` 指定仅运维账号可读的 curl 配置（`url = "https://实际告警地址"`，按接收方要求加认证头）。接收端处理 JSON 的 `service`、`job` 和 `exit`；投递失败另记日志。告警通道独立于验证码邮箱。

每次运行探测时，SMTP 连接或认证不可用即报警，即使窗口内无人发码。默认取最近 15 分钟内受理且已有结果的投递，至少 5 次、失败比例达到 20% 时报警；旧流水、未完成及被限流的请求不计入分母。可用 `--window-minutes`、`--min-attempts`、`--failure-percent` 调整。SMTP 接受投递后，实际到信仍取决于收件服务器。

## 3. 备份与恢复

调度主机安装与数据库主版本匹配的 `pg_dump`、`pg_restore`、`createdb` 和 Python 3.10+。备份角色须能读取目标库全部所需数据。备份按数据库分目录，每份含 `database.dump` 及 SHA-256 校验值。只有完整备份成功后才轮换，保留期至少 30 天。备份目录限制访问，定期将成功副本复制到独立、加密的存储。数据库归档不含集群角色和私有简历文件，部署方须另行保存角色配置，并在暂停写入与清理期间取得配套的私有文件快照。

```sh
set -a
. /etc/jimeet/ops.env
set +a
python3 backend/deploy/db_backup.py backup --directory "$JIMEET_BACKUP_DIR"
# SNAPSHOT 填写上条命令输出的备份目录。恢复角色须有建库权限。
python3 backend/deploy/db_backup.py restore "$SNAPSHOT" jimeet_restore_check
```

恢复先校验摘要，再创建指定的新库并在一个事务中恢复数据。目标已存在即停止；恢复中断时原库保持在线，新建空库留给运维检查。恢复对象由恢复角色持有，按部署角色重新授权。在隔离实例核对迁移、关键行及关联的私有文件，按当前时刻执行留存任务，并核对备份点以后的注销和删除记录，完成权限复核后再切换连接。备份里的历史身份或已撤销权限不得随回切重新开放。[PostgreSQL 恢复说明](https://www.postgresql.org/docs/15/app-pgrestore.html)
