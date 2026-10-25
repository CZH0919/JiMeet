# A 的实现任务（给编码智能体）

你负责 JiMeet 后端的底层：数据表、公共功能、状态机、权限判断、文件存储、通知与审计。B、C 的业务接口不是你写的，你只提供他们调用的接口。

唯一依据：[database.md](database.md)。表、字段、约束名以它为准，不得自行改动设计。若认为必须改，先停下来向用户说明，得到明确同意后才能改。

## 1 技术基线

- Python >= 3.12，Django 6.1，PostgreSQL 14+，`psycopg[binary]` 3.x，Django REST Framework。依赖固定版本。
- 会话：Django session cookie + CSRF。`HttpOnly`、`Secure`、`SameSite=Lax`。
- 定时任务：management command + cron，不引入 Celery。
- `TIME_ZONE="Asia/Shanghai"`，`USE_TZ=True`，`ATOMIC_REQUESTS=False`，`AUTH_USER_MODEL="accounts.User"`。
- 认证凭证（SSO ticket、会话 key）不落库、不写日志。

## 2 你拥有的文件

```
backend/
├─ manage.py, requirements/, .env.example
├─ config/settings/{base,dev,prod,test}.py, config/urls.py
├─ apps/core/          choices clock errors responses exception_handler pagination permissions tx middleware health
├─ apps/accounts/      models identity sso services backends views urls admin
├─ apps/recruitments/  models rules policies state retention        （只有这五个文件归你）
├─ apps/applications/  models policies                              （只有这两个文件归你）
├─ apps/notifications/ models types templates service mail jobs
├─ apps/files/         storage validators jobs
├─ apps/chat/          models                                       （只有 models）
├─ apps/audit/         models service actions
└─ tests/base.py       TransactionTestCase 基类、工厂、登录辅助
```

各 app 的 `services.py`、`selectors.py`、`serializers.py`、`views.py`、`urls.py`（accounts 除外）不是你的，不要写。所有 `migrations/` 只由你生成。

依赖方向：`views → services/selectors → policies/rules → models`，不得反向。`rules.py`、`policies.py` 只写纯函数，不访问数据库。

## 3 表与约束

按 database.md 逐表建模，`db_table` 显式指定，约束名和索引名与文档一致。

| database.md | 模型 / db_table | 要点 |
|---|---|---|
| 1.1 | accounts.User / `app_user` | `Lower(email)` 唯一索引 `user_email_lower_uniq`；`user_login_method_chk`；`uid`、`real_id` 唯一；`sso_subject` 唯一可空；`password` 覆盖为 `NOT NULL DEFAULT ''` |
| 1.2 | recruitments.Recruitment / `recruitment` | 五个表级 CHECK：`recruitment_full_chk`、`recruitment_closed_time_chk`、`recruitment_full_time_chk`、`recruitment_close_pair_chk`、`recruitment_cleanup_pair_chk`；人数范围 CHECK；五个部分索引；`pg_trgm` 的 GIN 索引放独立迁移 |
| 1.3 | Tag / `tag`；RecruitmentTag / `recruitment_tag` | 显式 `through` 模型；`UNIQUE(recruitment, tag)` |
| 1.4 | applications.Application / `application` | `application_decided_chk`；部分唯一索引 `application_active_uniq`（`status <> 'withdrawn'`）；`resume_size <= 10485760`；两个普通索引 |
| 1.5 | notifications.Notification / `notification` | 索引 `(recipient, is_read, -created_at)`；`type` 不加 CHECK |
| 1.6 | notifications.EmailLog / `email_log` | `status` CHECK；`0 <= attempts <= 3` |
| 1.7 | chat.ChatConversation / `chat_conversation`；ChatMessage / `chat_message` | `user_low < user_high` CHECK；`UNIQUE(user_low, user_high)`；索引 `(conversation, created_at)` |
| 1.8 | audit.AuditLog / `audit_log` | `actor_id`、`target_id` 可空；`actor_role`、`actor_is_admin` 与 `actor_id` 同为空或同非空的 CHECK；`action` 不加 CHECK |

通用规则：
- 所有外键 `on_delete=models.PROTECT`。
- 枚举用 `TextChoices` + `CheckConstraint`，取值只来自 `core/choices.py`：`Role`、`RecruitmentType`、`RecruitmentStatus`、`CloseReason`、`ApplicationStatus`、`PublisherMark`、`ResumeType`、`EmailStatus`。
- 默认值用 `db_default`。`updated_at` 用 `auto_now`，批量 `update()` 必须显式写 `updated_at`。
- 迁移后用 `\d+ <table>` 与 database.md 逐表核对。

## 4 core 公共底层

- `clock.now()`：业务代码禁止直接调用 `timezone.now()`，测试可冻结。
- `errors.py`：`BizError(code, http_status, message, details)` 及子类 `NotAuthenticated`、`Forbidden`、`NotFound`、`ValidationFailed`、`Conflict`；`NotFoundAsDenied` 响应 404 但记审计 `permission_denied`。
- `responses.py`：`ok(data)`、`created(data)`、`page(items, page, page_size, total)`。
- `exception_handler.py`：`BizError`、校验错误、未捕获异常统一成信封；对拒绝类异常在事务之外调用 `audit.record(action="permission_denied")`，避免被业务回滚吞掉。
- `pagination.py`：`page` 默认 1，`page_size` 默认 20，最大 50。
- `permissions.py`：`IsAuthenticatedBiz`、`IsAdminFlag`（读 `is_admin`，不用 `is_staff`）。
- `tx.py`：`assert_not_in_atomic()`、`assert_in_atomic()`、`lock_recruitment(id)`、`lock_application(id, recruitment)`（必须先锁招聘再锁申请）、`peek_application_recruitment_id(id)`（只读，不用其状态做决定）。
- `middleware.py`：生成 `request_id`，日志不含 cookie、token、简历内容。
- `health.py`：`GET /healthz` 检查数据库连通。

### 统一信封

```json
{ "code": "OK", "message": "", "data": {}, "request_id": "..." }
```

失败时 HTTP 4xx/5xx，`code` 为错误码，`message` 为中文提示，字段错误放 `data.details`。列表 `data = {items, page, page_size, total}`。

### 错误码

OK、UNAUTHENTICATED(401)、FORBIDDEN(403)、NOT_FOUND(404)、VALIDATION_ERROR(400)、PRIVACY_NOT_CONSENTED(403)、SELF_APPLICATION_FORBIDDEN(403)、RECRUITMENT_NOT_OPEN(409)、RECRUITMENT_NOT_EDITABLE(409)、RECRUITMENT_FULL(409)、PROCESSING_WINDOW_CLOSED(409)、HEADCOUNT_BELOW_ACCEPTED(409)、DUPLICATE_APPLICATION(409)、APPLICATION_NOT_PROCESSING(409)、INVALID_RESUME_FILE(400，`details.reason` 为 type/size/signature)、AUTH_FAILED(401)、SSO_UNAVAILABLE(503)、INTERNAL_ERROR(500)。

无权访问他人的申请、会话一律 404；对象可见但操作不允许才用 403。

## 5 accounts

- `User`：继承 `AbstractBaseUser` + `PermissionsMixin`，`USERNAME_FIELD="real_id"`。管理员权限只用 `is_admin`，`is_staff`/`is_superuser` 仅供 Django Admin。
- `identity.py`：`resolve_role(real_id) -> Role`、`is_tongji_email(email) -> bool`。规则待用户给出，先留接口和 TODO，不要猜测。
- `sso.py`：`SSOProvider` 抽象，`authorize_url(state)`、`exchange(callback_params) -> SSOIdentity(real_id, name, email, subject)`。实现 `CasSSOProvider`（待学校规范）和 `DevSSOProvider`。超时不超过 5 秒；不可用抛 `SSO_UNAVAILABLE`，不降级为密码登录。
- `services.py`：`login_with_sso(identity)`（首次登录建用户，`nickname` 默认取姓名，必要信息缺失拒绝）、`update_profile(user, nickname=None, email_notify_enabled=None)`、`give_privacy_consent(user)`。
- `backends.py`：按 `sso_subject` 或 `real_id` 取用户，检查 `is_active`；启用密码登录时检查 `has_usable_password()`。
- 接口（你自己实现）：`GET /api/v1/auth/sso/login`、`GET /auth/sso/callback`、`POST /auth/logout`、`GET /auth/csrf`、`POST /auth/dev-login`（仅 `DEBUG` 且 `ALLOW_DEV_LOGIN=True`，prod 启动时断言关闭）、`GET /me`、`PATCH /me`、`POST /me/privacy-consent`、`GET /healthz`。
- `admin.py` 注册 User、Tag；不注册 chat 的两个模型。

## 6 recruitments：rules、policies、state、retention

### rules.py（纯函数，一律用传入的 now）

```python
seven_day_deadline(r) -> datetime | None        # closed_at + 7 天
retention_starts_at(r) -> datetime | None       # closed_at、full_at、deleted_at 中最早的非空者
retention_expires_at(r) -> datetime | None      # 起算点 + 180 天
is_retention_expired(r, now) -> bool
is_apply_open(r, now) -> bool                   # 未删除、open、now < deadline
is_processable(r, now) -> bool                  # 未删除；open 且未过期，或 closed 且 now < closed_at + 7 天；full 为否
is_editable(r, now) -> bool                     # 未删除、open、now < deadline
is_publisher_deletable(r, now) -> bool
```

### policies.py

`can_edit(user, r, now)`、`can_close(user, r, now)`（发布者、open、未满员）、`can_delete(user, r, now)`（发布者：`is_publisher_deletable`；管理员：只要未删除）、`can_view_applications(user, r)`（仅发布者，管理员无特权）。

### state.py

```python
@dataclass(frozen=True)
class SyncResult:
    closed: bool
    auto_rejected: int
    became_full: bool

def sync_recruitment(recruitment_id, *, now=None) -> SyncResult:
    """事务一，自带 atomic，入口 assert_not_in_atomic，幂等。
    锁招聘行；已删除则返回。
    open 且 now >= deadline：置 closed，closed_at=deadline，close_reason='deadline'。
    closed 且 now >= closed_at+7天：批量拒绝仍为 processing 的申请，
    decided_at=closed_at+7天，并通知申请人。"""

def mark_full(recruitment, now) -> None:
    """已持有招聘锁时调用。同一条 UPDATE 写 status='full' 与 full_at=now。
    若此时仍是 open 且已过 deadline，补记 closed_at/close_reason 但不覆盖 full；
    已有手动关闭时间与原因不变。批量拒绝其余 processing 申请，decided_at=full_at，并通知。"""

def reject_processing_applications(recruitment, decided_at, reason) -> int:
    """批量 UPDATE 必须显式写 updated_at。"""

def run_in_recruitment_tx(recruitment_id, fn):
    """1. assert_not_in_atomic()  2. now = clock.now()，整个请求只取一次
    3. sync_recruitment(recruitment_id, now=now)   # 事务一，先提交
    4. with transaction.atomic(): r = lock_recruitment(...); return fn(r, now)   # 事务二
    业务异常只回滚事务二，补执行保持已提交。不使用 savepoint 包住补执行。"""
```

规则要点：
- 自动处理的时间取业务时间：到期关闭取 `deadline`，七天自动拒绝取 `closed_at + 7 天`，满员拒绝取 `full_at`。通知的 `created_at` 是真实创建时间。
- 仅实际发生状态变更时才通知和计数，重复执行不重复。
- 调整人数上限使其等于 `accepted_count` 时，必须在同一次 UPDATE 写 `status='full'` 和 `full_at`，否则违反 CHECK。

### retention.py

```python
def purge_expired_applications(recruitment_id, *, now=None) -> bool:
    """1. sync_recruitment 补执行，确保无遗留 processing（事务一）
    2. 校验 is_retention_expired 且 applications_anonymized_at 为空，否则返回 False
    3. 删除所有关联简历文件（不存在视为成功）；任一失败则放弃，等下次重试
    4. 事务二：锁招聘 → 汇总五种状态数量写入 application_status_counts
       → 先删 EmailLog → 再删 Notification
         （application_id 指向这些申请的，以及 recruitment_id 指向本招聘且 type 以 'application_' 开头的）
       → 最后删全部 Application（含撤回的旧记录）→ 写 applications_anonymized_at。计数与标记同一事务。
    5. 已完成的不覆盖已有统计。"""
```

## 7 applications：policies

```python
@dataclass(frozen=True)
class ApplicationAccess:
    relation: Literal["applicant", "publisher", "none"]
    can_view: bool
    can_see_note: bool
    can_download_resume: bool
    can_see_publisher_mark: bool     # 仅发布者

def resolve_application_access(user, app, recruitment, now) -> ApplicationAccess
def can_submit_application(user, recruitment, now) -> None      # 不满足抛带具体错误码的 BizError
def can_modify_application(user, app, recruitment) -> bool      # 申请人本人、processing、招聘未删除
def can_withdraw_application(user, app, recruitment) -> bool    # 同上
def can_process_application(user, app, recruitment, now) -> bool  # 发布者、is_processable、processing
```

权限规则：
- 管理员身份不加权，只按是不是发布者或申请人判断。
- 到留存期限后双方都不可见。
- `withdrawn`、`invalid`：不返回简历文件；发布者也看不到 `note`；申请人仍可看自己的记录状态。
- `can_submit_application` 校验：申请人不是发布者、`privacy_consented_at` 非空、招聘未删除、`is_apply_open`、未重复投递。

## 8 notifications

- `types.py`：通知类型常量，申请事件类型统一以 `application_` 开头（清理依赖该前缀）。写一条单元测试保证这一点。
- `templates.py`：`render(type, context) -> (title, content)`，只使用招聘名称、状态、站内链接，不接收简历内容与申请人完整个人信息。
- `service.py`：

```python
def notify(*, recipient, type, recruitment, application=None, context=None) -> Notification | None:
    """必须在 atomic 内调用（assert_in_atomic）。
    申请相关通知必须同时给 recruitment 与 application。
    招聘已过留存期限时不生成申请相关通知，返回 None。
    recipient.email_notify_enabled 为真时，同一事务内创建 pending 的 EmailLog，
    并用 transaction.on_commit 触发首次发送，不在事务内发邮件。"""
```

- `mail.py`：`send_email_log(email_log_id)`、`retry_pending_emails(limit)`。
  - 创建时 `status='pending'`、`attempts=0`、`last_error=NULL`。
  - 发送前 `select_for_update(skip_locked=True)`，拿不到锁就跳过。
  - 发送前重新检查：通知仍存在、招聘未过留存期限、状态仍为 `pending`。
  - `last_error IS NOT NULL` 说明是重试，先 `attempts += 1` 再发；否则是首次，`attempts` 保持 0。
  - 成功置 `sent`。失败写 `last_error`，`attempts == 3` 置 `failed`，否则保持 `pending`。
  - 重试时机用 `updated_at` 与退避表比较（`attempts` 为 0/1/2 时等待 1/5/30 分钟）。
  - 进入 `failed` 时写 ERROR 级日志。
  - 邮件正文只含状态变更类型、关联名称、当前状态与站内链接；错误日志不存简历内容、凭证、完整邮件正文。

## 9 files

```python
@dataclass(frozen=True)
class StoredResume:
    path: str; original_name: str; size: int; type: str   # type: 'pdf'|'doc'|'docx'

def validate_resume(upload) -> None
    # 扩展名 + 文件头特征 + 大小（<=10MB），不信任 Content-Type；失败抛 INVALID_RESUME_FILE
def save_resume(upload) -> StoredResume
    # 随机名写入 PRIVATE_FILE_ROOT/resumes/YYYY/MM/<uuid>.<ext>，绝不用用户文件名拼路径；必须在 atomic 之外调用
@contextmanager
def staged_resume(upload) -> Iterator[StoredResume]
    # with 块内抛异常则 discard 新文件再重新抛出
def discard_resume(path) -> bool
    # 不存在视为成功；失败只记日志并返回 False，不抛异常
def open_resume(path) -> BinaryIO
def cleanup_orphans(*, older_than=timedelta(hours=24), referenced) -> CleanupReport
    # 删除 resumes/ 下未被引用且 mtime 超过 24 小时的文件；referenced 由调用方分批查询传入
```

- `PRIVATE_FILE_ROOT` 在 Web 静态目录与 `MEDIA_ROOT` 之外，不配置任何直链路由。
- 文件一次写入最终路径，不做暂存目录搬动；整个 `resumes/` 目录是清理扫描范围。
- 替换简历后旧文件删除失败，靠 `cleanup_orphans` 兜底，不另建待删除表。
- 简历下载接口由 C 写，你只提供 `open_resume` 和 `resolve_application_access`。

## 10 audit

```python
def record(*, actor, action, target_type, target_id, reason=None) -> AuditLog
    # actor_role / actor_is_admin 在函数内从 actor 快照；actor 为 None 时二者同为 None
    # reason 之外不接受自由文本，不得放入原始文件名、补充说明、认证凭证
```

`audit/actions.py`：`recruitment_delete`、`admin_delete`、`resume_view`、`application_update`、`permission_denied`。业务审计在业务事务内调用，与业务同提交；权限拒绝审计在事务外由异常处理器调用。日志只追加，不提供修改和删除接口。

## 11 定时任务（management command）

| 命令 | 作用 | 扫描条件 |
|---|---|---|
| `run_sync_recruitments` | 到期关闭、七天自动拒绝 | open 且未删除且 `deadline <= now`；closed 且未删除且 `closed_at <= now-7d` 且有 processing 申请。逐个调用 `sync_recruitment` |
| `run_purge_applications` | 180 天申请清理 | `applications_anonymized_at IS NULL` 且 `LEAST(closed_at, full_at, deleted_at) <= now-180d`。逐个调用 `purge_expired_applications` |
| `run_send_emails` | 邮件首次发送兜底与重试 | `status='pending'`，按第 8 节 |
| `run_cleanup_orphan_files` | 孤立简历文件 | 未被引用且 mtime 超过 24 小时 |
| `run_cleanup_audit_logs` | 审计日志留存 | 仅删除 `created_at` 满一年的记录 |

每个招聘单独开事务，一条失败不影响其他条。

## 12 测试

- 涉及加锁、并发、补执行的测试继承 `tests/base.py` 的 `TransactionTestCase` 子类，不用被外层事务包住的 `TestCase`。
- `rules.py`、`policies.py` 用 `SimpleTestCase`。
- 必须覆盖：重复接受同一申请不重复加人数、接受与撤回并发、超员、任务延迟后接口仍正确、补执行在业务拒绝后仍已提交、权限拒绝路径、`application_` 前缀。
- 每个 service 至少三条路径：成功、权限拒绝、状态不符。

## 13 交付顺序

1. 项目骨架、`settings`、`core`、全部 `models.py` 与迁移、`dev-login`、`/me`、测试基类与工厂。
2. `rules.py`、`policies.py`、`state.py`、`files/storage.py`、`notify`、`audit.record`。完成后 B、C 即可开工。
3. `mail.py`、`retention.py`、全部定时命令、SSO 正式实现、`/healthz`。
4. 并发与补执行的 `TransactionTestCase` 用例。

## 14 未确定项（不要自行猜测）

- 学号/工号判定规则、同济邮箱域名白名单：`identity.py` 留 TODO。
- `max_headcount` 的应用层上限：留成配置常量，暂不设值。
- `PermissionsMixin` 会多出 `is_superuser` 列以及 `app_user_groups`、`app_user_user_permissions` 两张表，与 database.md 的 1.1 不一致，建模前先向用户确认处理方式。
