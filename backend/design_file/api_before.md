# jiMeet 后端接口文档（A 部分）

本文保留 A 阶段公共接口与环境搭建说明，作为历史版本存档。Sprint1 招募、申请、简历和通知的当前完整接口契约见 [api.md](api.md)。

## 1 已完成与预留

### 1.1 已完成

- 数据库：10 张业务表的模型、迁移、约束与索引（用户、招聘、标签、招聘标签、申请、通知、邮件记录、审计、会话、消息），PostgreSQL 的 pg_trgm 搜索索引。
- 公共底层：统一响应信封、错误码、异常处理、请求 ID、分页工具、权限基类、事务与行锁工具、可冻结的时钟。
- 招聘规则：截止时间与人数校验、开放/关闭/满员判定、七天处理窗口、180 天留存判定、招聘与申请的权限策略。
- 状态流转：到期关闭、七天后自动拒绝、满员自动拒绝、`run_in_recruitment_tx` 两段事务入口。
- 简历文件：类型/大小/文件头校验、私有目录存储、失败清理、孤立文件清理函数。
- 通知与审计：站内通知、邮件待发送记录（提交后调度）、审计日志与身份快照。
- 账号：开发登录、会话、CSRF、个人资料、隐私告知确认。
- 命令：`seed_tags`（19 个预设领域）、`run_sync_recruitments`（补执行到期关闭与自动拒绝）。
- 测试：173 项自动化测试，含 PostgreSQL 行锁并发用例。

### 1.2 预留

- 招聘发布、投递、处理申请的 HTTP 接口（由 B 实现，调用上面的底层）。
- 简历下载、通知中心、聊天、推送（由 C 实现）。
- 学校统一身份认证（CAS）：`/auth/sso/login`、`/auth/sso/callback` 当前返回 501。
- 邮件真实发送与重试：`dispatch` 目前只写日志。
- 命令 `run_send_emails`、`run_purge_applications`、`run_cleanup_orphan_files`、`run_cleanup_audit_logs`：已注册，执行会报 `CommandError: reserved`。
- 身份规则：`resolve_role` 目前按学号/工号首字母 `t` 判教师，是开发期占位。

### 1.3 环境搭建与迁移

依赖：Python 3.12+、PostgreSQL 15+。Django 6.1.2、DRF 3.18.3、psycopg 3.3.6 已固定在 `backend/requirements/base.txt`。完整的系统层步骤见 `file/django-env-setup.md`，下面只写本仓库的构建流程。

配置全部读环境变量，不会自动加载 `.env`。`backend/.env.example` 列出了变量名，使用前自行导出，例如 `set -a; source .env; set +a`。

#### macOS

```bash
brew install python@3.12 postgresql@18
brew services start postgresql@18

# 建角色与库（jimeet 需要 CREATEDB，测试会创建 test_jimeet）
psql -d postgres -c "CREATE ROLE jimeet LOGIN PASSWORD 'jimeet' CREATEDB;"
createdb -O jimeet jimeet

cd backend
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements/base.txt

cp .env.example .env          # 填 DB_PASSWORD 等，然后导出
set -a; source .env; set +a

python manage.py check
python manage.py migrate      # 按 accounts → recruitments → applications → notifications → audit → chat 的依赖自动排序
python manage.py seed_tags    # 可重复执行
python manage.py runserver 127.0.0.1:8000
```

#### Ubuntu

```bash
sudo apt update

# 先确认 Python 3.12 是否已经安装；Ubuntu 22.04 默认软件源可能没有 python3.12。
python3.12 --version
# 如果上面的命令不存在，请先用 pyenv 或其他方式安装 Python 3.12，
# 不要把“找不到 python3.12”误认为 venv 创建失败。

# Django 6.1.2 要求 PostgreSQL 15+。Ubuntu 默认仓库可能只有 PostgreSQL 14，
# 此时应使用 PostgreSQL PGDG 软件源安装 postgresql-15，或升级现有集群。
sudo apt install -y curl ca-certificates gnupg
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | sudo gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg
echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" \
  | sudo tee /etc/apt/sources.list.d/pgdg.list
sudo apt update
sudo apt install -y postgresql-15 postgresql-client-15 postgresql-contrib libpq5
sudo systemctl enable --now postgresql

# 如果机器上已有 PostgreSQL 14 的 main 集群，安装 15 后先迁移：
# sudo pg_upgradecluster -v 15 14 main
# 确认 pg_lsclusters 后再考虑清理旧集群；不要直接删除仍有数据的集群。

# 首次配置执行；若提示角色或数据库已存在，说明之前已经创建过，可继续。
cd /tmp
sudo -u postgres psql -d postgres -c "CREATE ROLE jimeet LOGIN PASSWORD 'jimeet' CREATEDB;"
sudo -u postgres createdb -O jimeet jimeet

cd ~/桌面/jimeet/jiMeet/backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements/base.txt

# .env 不会被 Django 自动加载；复制后必须填写 DB_PASSWORD 和 DJANGO_SECRET_KEY。
cp .env.example .env
# DB_PASSWORD 必须与上面 CREATE ROLE 使用的密码一致；DJANGO_SECRET_KEY 使用随机长字符串。
# 例如可用下面命令生成密钥，然后将结果填入 .env 的 DJANGO_SECRET_KEY= 行。
python -c "import secrets; print(secrets.token_urlsafe(48))"

set -a; source .env; set +a

python manage.py check
python manage.py migrate
python manage.py seed_tags
python manage.py runserver 127.0.0.1:8000
```

两个系统共用的后续命令：

```bash
set -a; source .env; set +a       # 每个新终端都要执行；项目不会自动加载 .env
.venv/bin/python manage.py makemigrations --check --dry-run   # 模型与迁移一致时输出 No changes detected
.venv/bin/python manage.py test tests                         # 全量测试，期望 173 项 OK
.venv/bin/python manage.py run_sync_recruitments              # 手工补执行到期招聘（会修改数据）
.venv/bin/python manage.py createsuperuser                    # 需要进 Django Admin 时
```

生产环境：设置 `DJANGO_SETTINGS_MODULE=config.settings.prod`，并提供 `DJANGO_SECRET_KEY`、`DJANGO_ALLOWED_HOSTS`、`DB_NAME`、`DB_USER`、`DB_PASSWORD`、`DB_HOST`，缺任何一项启动即报错。`ALLOW_DEV_LOGIN` 在生产环境开启会直接报错。


启动服务需要
```bash
cd backend
set -a; source .env; set +a
.venv/bin/python manage.py runserver
```
---

## 2 接口

### 2.0 通用约定

地址前缀 `/api/v1`，路径不带末尾斜杠。请求与响应均为 JSON，字符集 UTF-8。

**响应信封**：所有接口（包括错误）都返回同一结构。

```json
{
  "code": "OK",
  "message": "",
  "data": { },
  "request_id": "0e6d34f95c554778a83848749e62c2d3"
}
```

| 字段 | 含义 |
|------|------|
| code | 成功为 `OK`，失败为 2.6 节的错误码 |
| message | 成功为空串，失败为中文提示，可直接展示 |
| data | 成功时的业务数据；失败时为 `null`，参数错误时为 `{"details": {...}}` |
| request_id | 本次请求 ID，同时出现在响应头 `X-Request-Id`，排查问题时提供给后端 |

请求头可带 `X-Request-Id`（1 到 64 位字母、数字、短横线）供全链路追踪，不合法或缺省时由服务端生成。

**登录态与 CSRF**：登录后服务端设置 `sessionid` Cookie。所有会改变数据的请求（POST、PATCH 等）必须带请求头 `X-CSRFToken`，值取自 Cookie `csrftoken`。登录会轮换 CSRF 令牌，登录后须重新读取。

**默认鉴权**：除标注“公开”的接口外，未登录一律返回 401 `UNAUTHENTICATED`。

下面的 curl 示例共用这段准备：

```bash
BASE=http://127.0.0.1:8000/api/v1
COOKIE=$(mktemp /tmp/jimeet-cookie.XXXXXX)
```

### 2.1 健康检查

**GET /healthz**（公开）

用于运维探活、负载均衡检查、部署后确认数据库可连通。

```bash
curl -i "$BASE/healthz"
```

| 情形 | HTTP | code | data |
|------|------|------|------|
| 数据库正常 | 200 | OK | `{"status": "ok"}` |
| 数据库连不上 | 503 | INTERNAL_ERROR | null，message 为“数据库不可用” |

### 2.2 会话：CSRF、登录、登出

用于前端启动时拿令牌、本地联调时登录、用户退出。

#### GET /auth/csrf（公开）

写入 `csrftoken` Cookie 并返回令牌。前端首次加载、登录前后各调用一次。

```bash
curl -sS -c "$COOKIE" "$BASE/auth/csrf"
TOKEN=$(awk '$6 == "csrftoken" {print $7}' "$COOKIE")
```

```json
{"code": "OK", "message": "", "data": {"csrf_token": "hURmPU…"}, "request_id": "…"}
```

#### POST /auth/dev-login（公开，仅开发环境）

开发与联调用的登录入口，用学号/工号直接登录，首次出现的编号会自动创建账号。仅当 `DEBUG` 与 `ALLOW_DEV_LOGIN` 同时为真时才注册路由，否则是 404。正式的统一身份认证接入后，这个入口不会出现在生产环境。

请求体：

| 字段 | 必填 | 说明 |
|------|------|------|
| real_id | 是 | 学号/工号，字母、数字、下划线、短横线，最长 32 位 |
| name | 否 | 真实姓名，最长 32 位，缺省取 `real_id` |
| email | 否 | 邮箱，缺省为 `<real_id>@tongji.edu.cn`，域名须在 `ALLOWED_EMAIL_DOMAINS` 内 |

出现其他字段会被拒绝。新建账号的昵称为 `同学_` 加 12 位随机字符，角色按编号规则判定，不是管理员。

```bash
curl -i -b "$COOKIE" -c "$COOKIE" -H "X-CSRFToken: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"real_id":"a_scenario_001","name":"小陈","email":"a_scenario_001@tongji.edu.cn"}' \
  "$BASE/auth/dev-login"
TOKEN=$(awk '$6 == "csrftoken" {print $7}' "$COOKIE")   # 登录后令牌已轮换
```

成功时 `data` 同 2.3 的本人资料。

| 情形 | HTTP | code |
|------|------|------|
| 成功 | 200 | OK |
| 缺少 CSRF 令牌 | 403 | FORBIDDEN |
| 字段缺失、格式错误或带未知字段 | 400 | VALIDATION_ERROR |
| 邮箱域名不允许、与已有账号的邮箱或编号冲突 | 401 | AUTH_FAILED |
| 账号已停用 | 403 | FORBIDDEN |
| 开关未开启 | 404 | NOT_FOUND |

#### POST /auth/logout

清除当前会话。需要登录与 CSRF 令牌。

```bash
curl -i -b "$COOKIE" -H "X-CSRFToken: $TOKEN" -X POST "$BASE/auth/logout"
```

成功：200，`data` 为 `null`。登出后再请求 `/me` 返回 401。

### 2.3 当前用户

用于个人主页、导航栏用户信息、发布与投递前的资格判断（是否已确认隐私告知）。

#### GET /me

返回本人资料。

```bash
curl -i -b "$COOKIE" "$BASE/me"
```

```json
{
  "code": "OK",
  "message": "",
  "data": {
    "uid": "3f9c…（32 位，对外标识）",
    "nickname": "山间清风",
    "name": "小陈",
    "role": "student",
    "is_admin": false,
    "email": "a_scenario_001@tongji.edu.cn",
    "email_notify_enabled": true,
    "privacy_consented": false
  },
  "request_id": "…"
}
```

| 字段 | 含义 |
|------|------|
| uid | 对外用户标识，不是数据库 id，也不是学号 |
| nickname | 昵称，对他人展示 |
| name | 真实姓名，只在本人资料中返回 |
| role | `student` 或 `teacher` |
| is_admin | 是否有管理员权限，只能在 Django Admin 中修改 |
| email | 本人邮箱 |
| email_notify_enabled | 是否接收邮件通知，站内通知始终生成 |
| privacy_consented | 是否已确认个人信息处理告知；未确认时不能投递 |

数据库自增 id、学号/工号、统一认证标识不会出现在任何响应中。

#### PATCH /me

修改昵称与邮件通知开关，可只传其中一项。

```bash
curl -i -b "$COOKIE" -H "X-CSRFToken: $TOKEN" \
  -H 'Content-Type: application/json' -X PATCH \
  -d '{"nickname":"山间清风","email_notify_enabled":true}' "$BASE/me"
```

| 字段 | 规则 |
|------|------|
| nickname | 1 到 32 字，首尾空白会被去掉，不能为空白或 null |
| email_notify_enabled | 必须是 JSON 布尔值，`"false"` 这样的字符串会被拒绝 |

传入 `role`、`is_admin` 等其他字段一律 400，不会被静默忽略。

| 情形 | HTTP | code |
|------|------|------|
| 成功，`data` 为更新后的资料 | 200 | OK |
| 字段不合法 | 400 | VALIDATION_ERROR |
| 未登录 | 401 | UNAUTHENTICATED |
| 缺少 CSRF 令牌 | 403 | FORBIDDEN |

#### POST /me/privacy-consent

确认个人信息处理告知，首次确认时写入时间，重复调用不覆盖，可安全重试。投递简历前由前端引导用户调用。

```bash
curl -i -b "$COOKIE" -H "X-CSRFToken: $TOKEN" -X POST "$BASE/me/privacy-consent"
```

成功：200，`data` 为资料，`privacy_consented` 为 `true`。

### 2.4 预留接口

#### GET /auth/sso/login、GET /auth/sso/callback（公开）

学校统一身份认证的跳转与回调，等待学校提供正式规范后接入。当前返回：

```json
{"code": "INTERNAL_ERROR", "message": "预留", "data": null, "request_id": "…"}
```

HTTP 状态码 501。前端遇到 501 应显示“暂未开放”，不要当作服务故障上报。

### 2.5 其他通用响应

下面的情形不属于某个具体接口，所有接口都可能遇到。

| HTTP | code | 含义 |
|------|------|------|
| 400 | VALIDATION_ERROR | 参数不合法，`data.details` 按字段给出原因，见下例 |
| 401 | UNAUTHENTICATED | 未登录或会话过期 |
| 401 | AUTH_FAILED | 登录凭证无效 |
| 403 | FORBIDDEN | 无权操作，或 CSRF 校验失败 |
| 404 | NOT_FOUND | 对象不存在，或对无权访问者隐藏对象 |
| 405 | METHOD_NOT_ALLOWED | 请求方法不被该路径支持 |
| 500 | INTERNAL_ERROR | 未处理的服务端异常，响应不含堆栈，用 `request_id` 查日志 |

参数错误示例：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "参数校验失败",
  "data": {"details": {"is_admin": ["不允许的字段"]}},
  "request_id": "…"
}
```

注意：访问一个根本不存在的路径（如 `/api/v1/nope`）时，返回的是 Django 默认的 HTML 404 页面，不是信封。前端按 HTTP 状态码处理即可，不要对这类响应做 JSON 解析。

### 2.6 错误码表

`code` 是前端判断分支的依据，`message` 只用于展示。下表中“当前使用”的已有接口会返回，“预留”的会在 B、C 的业务接口里出现，含义已经固定。

| code | HTTP | 含义 | 状态 |
|------|------|------|------|
| OK | 200 / 201 | 成功 | 当前使用 |
| UNAUTHENTICATED | 401 | 未登录 | 当前使用 |
| AUTH_FAILED | 401 | 登录身份无效或冲突 | 当前使用 |
| FORBIDDEN | 403 | 无权操作，含 CSRF 失败、账号停用 | 当前使用 |
| NOT_FOUND | 404 | 对象不存在或不可见 | 当前使用 |
| VALIDATION_ERROR | 400 | 参数校验失败 | 当前使用 |
| METHOD_NOT_ALLOWED | 405 | 方法不允许 | 当前使用 |
| INTERNAL_ERROR | 500 / 501 / 503 | 服务端错误、功能预留、数据库不可用 | 当前使用 |
| PRIVACY_NOT_CONSENTED | 403 | 未确认个人信息处理告知，不能投递 | 预留 |
| SELF_APPLICATION_FORBIDDEN | 403 | 不能申请自己发布的招聘 | 预留 |
| RECRUITMENT_NOT_OPEN | 409 | 招聘已关闭、已满员或已过截止，不能投递 | 预留 |
| RECRUITMENT_NOT_EDITABLE | 409 | 招聘当前不可编辑 | 预留 |
| RECRUITMENT_FULL | 409 | 招聘已满员 | 预留 |
| PROCESSING_WINDOW_CLOSED | 409 | 关闭后七天处理窗口已结束 | 预留 |
| HEADCOUNT_BELOW_ACCEPTED | 409 | 人数上限不能低于已接受人数 | 预留 |
| DUPLICATE_APPLICATION | 409 | 已存在未撤回的申请 | 预留 |
| APPLICATION_NOT_PROCESSING | 409 | 申请已不是处理中，不能再处理 | 预留 |
| INVALID_RESUME_FILE | 400 | 简历文件不合格，`details.reason` 为 `type`、`size` 或 `signature` | 预留 |
| SSO_UNAVAILABLE | 503 | 统一身份认证不可用 | 预留 |

### 2.7 列表分页格式

分页工具已就绪，业务列表接口上线后统一使用。请求参数 `page`（默认 1）、`page_size`（默认 20，最大 50），非法值返回 400。

```json
{
  "code": "OK",
  "message": "",
  "data": {"items": [], "page": 1, "page_size": 20, "total": 0},
  "request_id": "…"
}
```

---

## 3 后端文件结构

```text
jiMeet/
├── backend/
│   ├── manage.py                     # Django 入口，默认读 config.settings.dev
│   ├── .env.example                  # 环境变量名清单（不含真实值）
│   ├── requirements/
│   │   └── base.txt                  # 固定版本的 Python 依赖
│   ├── config/
│   │   ├── urls.py                   # 总路由：admin、/api/v1/ 下挂 core 与 accounts
│   │   ├── asgi.py / wsgi.py         # 部署入口
│   │   └── settings/
│   │       ├── base.py               # 公共配置：应用、数据库、会话、DRF、日志
│   │       ├── dev.py                # 开发：DEBUG 与开发登录默认开启
│   │       ├── prod.py               # 生产：缺环境变量即报错，禁用开发登录
│   │       └── test.py               # 测试：快速密码哈希、临时私有目录
│   ├── apps/
│   │   ├── core/                     # 公共底层
│   │   │   ├── choices.py            # 角色、招聘/申请状态等枚举
│   │   │   ├── clock.py              # 统一取时间，测试可冻结
│   │   │   ├── errors.py             # 错误码与业务异常
│   │   │   ├── exception_handler.py  # 异常转信封，拒绝类异常写审计
│   │   │   ├── responses.py          # ok / created / page 信封
│   │   │   ├── pagination.py         # page、page_size 解析
│   │   │   ├── permissions.py        # 登录与管理员标记权限
│   │   │   ├── middleware.py         # X-Request-Id 与日志上下文
│   │   │   ├── tx.py                 # 事务断言、招聘与申请行锁
│   │   │   ├── indexes.py            # 长名称索引的辅助类
│   │   │   ├── health.py             # /healthz
│   │   │   └── urls.py               # core 路由
│   │   ├── accounts/                 # 账号
│   │   │   ├── models.py             # User 与 UserManager
│   │   │   ├── identity.py           # 角色判定（临时规则）、邮箱域名校验
│   │   │   ├── sso.py                # 身份数据类、认证提供方接口、开发提供方
│   │   │   ├── services.py           # SSO 登录、改资料、隐私确认
│   │   │   ├── backends.py           # 接收已验证身份的认证后端
│   │   │   ├── serializers.py        # 请求校验与本人资料输出
│   │   │   ├── views.py              # CSRF、登录、登出、/me、SSO 预留
│   │   │   ├── urls.py               # 账号路由
│   │   │   └── admin.py              # Django Admin 用户管理
│   │   ├── recruitments/             # 招聘
│   │   │   ├── models.py             # Recruitment、Tag、RecruitmentTag
│   │   │   ├── rules.py              # 时间与人数规则、窗口与留存判定
│   │   │   ├── policies.py           # 编辑、关闭、删除、查看申请的权限
│   │   │   ├── state.py              # 到期关闭、满员、自动拒绝、两段事务入口
│   │   │   ├── retention.py          # 180 天留存清理（预留）
│   │   │   ├── seed.py               # 19 个预设领域
│   │   │   ├── admin.py              # 标签管理
│   │   │   └── management/commands/
│   │   │       ├── seed_tags.py              # 初始化预设标签，可重复执行
│   │   │       ├── run_sync_recruitments.py  # 补执行到期招聘
│   │   │       └── run_purge_applications.py # 留存清理（预留）
│   │   ├── applications/             # 申请
│   │   │   ├── models.py             # Application
│   │   │   └── policies.py           # 提交、修改、撤回、处理、字段可见性
│   │   ├── notifications/            # 通知
│   │   │   ├── models.py             # Notification、EmailLog
│   │   │   ├── types.py              # 通知类型常量
│   │   │   ├── templates.py          # 通知文案，限制可用字段
│   │   │   ├── service.py            # notify：站内通知与邮件待发送记录
│   │   │   ├── mail.py               # 邮件调度入口（本周只记日志）
│   │   │   └── management/commands/run_send_emails.py   # 邮件发送重试（预留）
│   │   ├── files/                    # 简历文件
│   │   │   ├── validators.py         # 类型、大小、文件头、展示名清洗
│   │   │   ├── storage.py            # 私有目录存取、暂存、孤立文件清理函数
│   │   │   ├── jobs.py               # 文件相关任务（预留）
│   │   │   └── management/commands/run_cleanup_orphan_files.py  # 孤立文件清理（预留）
│   │   ├── audit/                    # 审计
│   │   │   ├── models.py             # AuditLog，实例不可改不可删
│   │   │   ├── actions.py            # 审计动作常量
│   │   │   ├── service.py            # record：写入审计与身份快照
│   │   │   └── management/commands/run_cleanup_audit_logs.py    # 留存清理（预留）
│   │   └── chat/
│   │       └── models.py             # ChatConversation、ChatMessage（仅数据表）
│   │   # 各 app 的 migrations/ 为 Django 迁移，recruitments 另有 0002 搜索索引迁移
│   ├── tests/                        # 173 项自动化测试
│   │   ├── base.py / factories.py    # 测试基类与数据工厂
│   │   ├── core/                     # 公共底层测试
│   │   ├── accounts/                 # 登录、资料、接口测试
│   │   ├── recruitments/             # 规则、状态流转（含并发）、同步命令
│   │   ├── applications/             # 权限判定表
│   │   ├── notifications/            # 通知与邮件记录
│   │   ├── audit/                    # 审计
│   │   ├── files/                    # 文件校验与存储
│   │   ├── contract/                 # 发布→投递→接受→满员的端到端参考流程
│   │   └── test_*.py                 # 数据库约束、表结构、Admin、预设标签、预留命令
│   ├── file/
│   │   ├── api_before.md             # 本历史文档
│   │   └── design_manuscript/        # 设计稿、实施计划、验收清单与场景测试记录
│   └── var/                          # 运行产物（git 忽略）：私有简历目录、验证日志
├── database/                         # 预留目录，当前为空
├── frontend/                         # 预留目录，当前为空
└── file/
    └── django-env-setup.md           # macOS / Ubuntu 的系统环境搭建手册
```
