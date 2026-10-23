# JiMeet 后端实现规划（底层 + 数据库 ↔ 应用接口）

> 状态：草案，待 A 审核。本文只规划实现，不改动 [database.md](database.md) 的设计。
> 与 database.md 在转化中产生的出入、以及需要 A 定夺的事项，集中在第 9 章。

## 0 范围与分工

A（后端架构）负责：数据库表与约束、接口格式、状态与权限规则、登录鉴权、统一返回、文件存储、消息发送等公共底层。
B（核心业务后端）负责：招聘的发布/修改/删除/查看，申请的提交/处理，满员与并发正确性。
C（扩展功能后端）负责：简历文件的读取权限控制、通知中心、聊天、推荐（第一版按时间）。
D、E、F（前端、测试部署）不在本文范围，但接口约定（第 6、7 章）是他们的依据。

协作原则：B 和 C 只通过本文规定的 Python 接口（第 4 章）使用底层，不直接改 `models.py`、迁移文件、`core/`、`accounts/`、`audit/`、`files/storage.py`。需要新字段或新规则，先走第 3.3 节的变更流程。

## 1 技术基线

- Python >= 3.12，Django 6.1，PostgreSQL 14+，驱动 `psycopg[binary]` 3.x（见 [django-env-setup.md](../../../file/django-env-setup.md)）。
- 接口层建议用 Django REST Framework（待定，见 9.1）。本文的接口约定按 DRF 写。
- 会话采用 Django session cookie + CSRF（待定，见 9.3）。
- 定时任务采用 management command + cron，不引入 Redis/Celery（待定，见 9.2）。
- 时区：`TIME_ZONE = "Asia/Shanghai"`，`USE_TZ = True`，库内存 UTC，接口输出带偏移的 ISO 8601。
- `ATOMIC_REQUESTS = False`（database.md 0 第 8 条）。
- 依赖全部固定版本，写入 `requirements/base.txt`，不写开放区间。

## 2 目录结构与归属

```
backend/
├─ manage.py
├─ requirements/{base.txt, dev.txt}
├─ .env.example                       # 数据库、SSO、邮件、文件根目录等，不提交真实值
├─ config/
│  ├─ settings/{base,dev,prod,test}.py   [A]
│  ├─ urls.py                            [A] 统一挂载 /api/v1/ 下各 app 的 urls
│  └─ wsgi.py / asgi.py                  [A]
├─ apps/
│  ├─ core/            [A] 公共底层：返回格式、错误、事务、时钟、权限基类、枚举
│  ├─ accounts/        [A] User、登录、会话、个人资料
│  ├─ recruitments/    models/rules/state/retention [A]；services/selectors/serializers/views/urls [B]
│  ├─ applications/    models/policies [A]；services/selectors/serializers/views/urls [B]
│  ├─ notifications/   models/service/mail/templates/jobs [A]；views/serializers/urls [C]
│  ├─ files/           storage/validators/jobs [A]；下载 views/urls [C]
│  ├─ chat/            models [A]；services/views/serializers/urls [C]
│  ├─ audit/           models/service [A]
│  └─ feed/            [C] 推荐入口，第一版转调招聘列表
└─ tests/
   ├─ core/ accounts/ recruitments/ applications/ notifications/ files/ chat/
   └─ conftest 或 base.py            [A] 提供 TransactionTestCase 基类、工厂、登录辅助
```

每个 app 的固定文件布局（有哪些就放哪些，不新增别的层级）：

| 文件 | 作用 | 谁可以 import 它 |
|------|------|-----------------|
| models.py | 表与约束，对应 database.md | 任何 app |
| rules.py | 纯函数：时间/状态判断，不访问数据库 | 任何 app |
| policies.py | 纯函数：谁能看、谁能改 | services、views |
| services.py | 写操作，负责事务、加锁、通知、审计 | views、jobs |
| selectors.py | 读操作，只查询不写 | views |
| serializers.py | 请求校验与响应字段 | views |
| views.py | 薄薄一层：解析请求、调 service、返回 | urls |
| urls.py | 路由 | config/urls.py |

依赖方向：`views → services/selectors → policies/rules → models`，不得反向。views 里不写业务判断，serializers 不写数据库。

## 3 协作规则

### 3.1 目录归属

仓库根加 `CODEOWNERS`（或在评审约定里写明）：`core/ accounts/ audit/ config/` 及各 app 的 `models.py`、`migrations/`、`rules.py`、`policies.py` 归 A；其余按第 2 章标注。

### 3.2 写操作的统一模式

凡是改动招聘或申请状态的操作，B 和 C 都只用下面这一个入口，不自己拼事务：

```python
# apps/recruitments/state.py [A]
def run_in_recruitment_tx(recruitment_id: int, fn: Callable[[Recruitment, datetime], T]) -> T:
    """
    1. assert_not_in_atomic()              # 调用方不得已在 atomic 中
    2. now = clock.now()                   # 整个请求只取一次
    3. sync_recruitment(recruitment_id, now=now)   # 事务一：补执行并提交
    4. with transaction.atomic():          # 事务二
           r = lock_recruitment(recruitment_id)    # select_for_update
           return fn(r, now)               # fn 内部重新读取申请并复核
    业务异常只回滚事务二，补执行保持已提交（database.md 0 第 7 条）。
    """
```

`fn` 内需要锁申请行时，先用 `lock_application(application_id, recruitment)`，顺序固定为先招聘后申请（0 第 5 条）。要先拿到 `recruitment_id` 时，用 `peek_application_recruitment_id(application_id)`，只读不锁，不用其状态做决定。

### 3.3 改表的流程

1. B/C 提需求（改什么、为什么）。
2. A 评估是否要同步改 database.md；改 database.md 需 A 自己确认。
3. A 改 `models.py` 并生成迁移，B/C 拉取后继续。
4. 迁移文件只由 A 生成和合并，避免迁移冲突。

### 3.4 测试约定

涉及加锁、并发、补执行的测试一律继承 `tests/base.py` 的 `TransactionTestCase` 子类（database.md 0 第 8 条）。纯函数（rules、policies）用普通 `SimpleTestCase`。每个新增的 service 至少覆盖：成功、权限拒绝、状态不符三条路径。

## 4 各文件的作用、内容与沟通对象

### 4.1 core（A）

| 文件 | 作用与内容 | 与谁沟通 |
|------|-----------|---------|
| core/choices.py | 所有 `TextChoices`：`Role`、`RecruitmentType`、`RecruitmentStatus`、`CloseReason`、`ApplicationStatus`、`PublisherMark`、`ResumeType`、`EmailStatus`。取值与 database.md 的 CHECK 完全一致 | 所有 models |
| core/clock.py | `now() -> datetime`（带时区），测试时可冻结。业务代码禁止直接调用 `timezone.now()` | services、jobs |
| core/errors.py | `BizError(code, http_status, message, details)` 及子类 `NotAuthenticated`、`Forbidden`、`NotFound`、`Conflict`、`ValidationFailed`；`NotFoundAsDenied`（响应 404 但记审计 `permission_denied`）。错误码表见 6.3 | 全部 |
| core/responses.py | `ok(data=None, *, status=200)`、`created(data)`、`page(items, page, page_size, total)`；统一信封见 6.1 | views |
| core/exception_handler.py | DRF 异常处理：`BizError`、校验错误、未捕获异常 → 统一信封；对 `Forbidden`、`NotAuthenticated`、`NotFoundAsDenied` 在事务之外调用 `audit.record(action="permission_denied")`，避免被业务事务回滚吞掉 | audit |
| core/pagination.py | 页码分页，`page`（默认 1）、`page_size`（默认 20，最大 50） | selectors、views |
| core/permissions.py | DRF 权限类：`IsAuthenticatedBiz`、`IsAdminFlag`（读 `user.is_admin`，不用 `is_staff`） | views |
| core/tx.py | `assert_not_in_atomic()`、`assert_in_atomic()`、`lock_recruitment(id)`、`lock_application(id, recruitment)`、`peek_application_recruitment_id(id)` | state、services |
| core/middleware.py | 给每个请求生成 `request_id`，写入响应信封和日志；日志中不得出现 cookie、token、简历内容 | 全部 |
| core/health.py | `GET /healthz`，检查数据库连通，供运维监控 | 运维 |
| core/models.py | 抽象基类（仅在需要时）。注意不是所有表都有 `updated_at`，见 9.6 | 各 models |

### 4.2 accounts（A）

| 文件 | 作用与内容 | 与谁沟通 |
|------|-----------|---------|
| models.py | `User`，对应 1.1。`db_table="app_user"`，`USERNAME_FIELD="real_id"`，`AUTH_USER_MODEL="accounts.User"` | 所有 app |
| identity.py | `resolve_role(real_id: str) -> Role`：由学号/工号判定学生/教师；`is_tongji_email(email) -> bool`。规则待定，见 9.7 | sso.py |
| sso.py | `SSOProvider` 抽象：`authorize_url(state) -> str`、`exchange(callback_params) -> SSOIdentity(real_id, name, email, subject)`。实现 `CasSSOProvider`（待学校规范）与开发用 `DevSSOProvider`。认证请求超时 ≤ 5 秒；服务不可用抛 `SSO_UNAVAILABLE`，不降级为密码登录 | services |
| services.py | `login_with_sso(identity) -> User`（首次登录建用户，`nickname` 默认取姓名，必填信息缺失拒绝）；`update_profile(user, nickname=None, email_notify_enabled=None)`；`give_privacy_consent(user)`。禁止把 ticket/token 落库或写日志 | views、audit |
| backends.py | Django `AuthenticationBackend`，按 `sso_subject` 或 `real_id` 取用户，并检查 `is_active`；启用密码登录时检查 `has_usable_password()` | settings |
| views.py / urls.py | 登录、回调、登出、CSRF、`/me`，见 7.1。`dev-login` 仅 `DEBUG=True` 且 `ALLOW_DEV_LOGIN=True` 时注册，`prod.py` 里强制关闭并启动时断言 | 前端 |
| admin.py | Django Admin 注册 User/Tag，供开发者维护；`is_admin` 只在此处授予 | 开发者 |

### 4.3 recruitments（models/rules/state/retention 为 A，其余为 B）

| 文件 | 作用与内容 | 与谁沟通 |
|------|-----------|---------|
| models.py [A] | `Recruitment`、`Tag`、`RecruitmentTag`，约束见第 5 章 | applications、notifications |
| rules.py [A] | 纯函数（全部以传入的 `now` 为准）：<br>`seven_day_deadline(r) -> datetime \| None`（`closed_at + 7 天`）<br>`retention_starts_at(r) -> datetime \| None`（`closed_at`、`full_at`、`deleted_at` 中最早的非空者）<br>`retention_expires_at(r) -> datetime \| None`（起算点 + 180 天）<br>`is_retention_expired(r, now) -> bool`<br>`is_apply_open(r, now) -> bool`（未删除、`open`、`now < deadline`）<br>`is_processable(r, now) -> bool`（未删除，`open` 且未过期，或 `closed` 且 `now < closed_at + 7 天`；`full` 为否）<br>`is_editable(r, now) -> bool`（未删除、`open`、`now < deadline`）<br>`is_publisher_deletable(r, now) -> bool` | policies、services、notifications |
| policies.py [A] | `can_edit(user, r, now)`、`can_close(user, r, now)`（未满员且 `open` 且为发布者）、`can_delete(user, r, now)`（发布者：`is_publisher_deletable`；管理员：只要未删除）、`can_view_applications(user, r)`（仅发布者，管理员无特权） | services、views |
| state.py [A] | 状态机的共享部分，见下方签名 | B 的 services、jobs |
| retention.py [A] | 180 天清理，见 4.8 | jobs |
| services.py [B] | `create_recruitment`、`update_recruitment`、`close_recruitment`、`delete_recruitment`（含把处理中与已接受的申请置 `invalid`、向发布者之外的未拒绝申请人发通知；管理员删除另向发布者发 `admin_removed`），全部走 `run_in_recruitment_tx` | state、policies、notifications、audit |
| selectors.py [B] | `list_recruitments(filters, user)`、`get_recruitment_for_user(id, user)`、`list_my_recruitments(user)`、`count_applications(recruitment)`（清理前用实时统计，清理后读 `application_status_counts`） | views |
| serializers.py / views.py / urls.py [B] | 见 7.3 | 前端 |

`state.py` 的接口（A 实现，B 调用）：

```python
@dataclass(frozen=True)
class SyncResult:
    closed: bool              # 本次是否发生到期关闭
    auto_rejected: int        # 本次自动拒绝的申请数
    became_full: bool

def sync_recruitment(recruitment_id: int, *, now: datetime | None = None) -> SyncResult:
    """事务一。自带 atomic，入口 assert_not_in_atomic。幂等，重复调用不重复通知。
    1. 锁招聘行；已删除则直接返回
    2. status=open 且 now >= deadline：置 closed，closed_at=deadline，close_reason='deadline'
    3. status=closed 且 now >= closed_at + 7 天：批量拒绝仍为 processing 的申请，
       decided_at = closed_at + 7 天，并通知申请人
    """

def mark_full(recruitment: Recruitment, now: datetime) -> None:
    """已持有招聘锁时调用。置 status='full'、full_at=now（同一条 UPDATE），
    若此时 open 且已过 deadline，同时补记 closed_at/close_reason，但不覆盖 full；
    批量拒绝其余 processing 申请，decided_at=full_at，并通知。"""

def reject_processing_applications(recruitment: Recruitment, decided_at: datetime, reason: str) -> int:
    """批量 UPDATE 必须显式写 updated_at（QuerySet.update 不触发 auto_now）。"""

def run_in_recruitment_tx(recruitment_id, fn): ...   # 见 3.2
```

### 4.4 applications（models/policies 为 A，其余为 B）

| 文件 | 作用与内容 | 与谁沟通 |
|------|-----------|---------|
| models.py [A] | `Application`，约束见第 5 章 | recruitments、notifications、files |
| policies.py [A] | 申请相关的唯一权限出口，见下方签名 | B 的 services/views、C 的下载视图 |
| services.py [B] | `submit_application`、`update_application`、`withdraw_application`、`accept_application`、`reject_application`、`set_publisher_mark`，规则见 1.4 设计细节 5、8、9 | state、policies、files.storage、notifications、audit |
| selectors.py [B] | `list_applications_of_recruitment(recruitment, user, status)`、`list_my_applications(user)`、`get_application_for_user(id, user)`（调用 `resolve_application_access` 过滤字段） | views |
| serializers.py / views.py / urls.py [B] | 见 7.4 | 前端 |

`policies.py` 的接口：

```python
@dataclass(frozen=True)
class ApplicationAccess:
    relation: Literal["applicant", "publisher", "none"]
    can_view: bool                  # 能否看到申请记录本身
    can_see_note: bool              # 补充说明
    can_download_resume: bool
    can_see_publisher_mark: bool    # 仅发布者

def resolve_application_access(user: User, app: Application, recruitment: Recruitment, now: datetime) -> ApplicationAccess:
    """规则（1.4 设计细节 7）：
    - 管理员身份不加权，只按是不是发布者/申请人判断
    - 到留存期限（is_retention_expired）后，双方都不可见
    - withdrawn / invalid：简历文件不可下载；发布者也看不到 note；申请人仍可看自己的记录状态
    """

def can_submit_application(user, recruitment, now) -> None:   # 不满足抛 BizError，带具体错误码
def can_modify_application(user, app, recruitment) -> bool:   # processing 且招聘未删除，申请人本人
def can_withdraw_application(user, app, recruitment) -> bool: # 同上
def can_process_application(user, app, recruitment, now) -> bool:  # 发布者 + is_processable + processing
```

### 4.5 notifications（models/service/mail/templates/jobs 为 A，views 为 C）

| 文件 | 作用与内容 | 与谁沟通 |
|------|-----------|---------|
| models.py [A] | `Notification`、`EmailLog`（1.5、1.6） | applications、recruitments |
| types.py [A] | 通知类型常量。申请事件类型统一以 `application_` 开头，清理逻辑依赖这个前缀（1.4 设计细节 6）。因为 `type` 不加 CHECK，这里是唯一取值来源 | templates、retention |
| templates.py [A] | `render(type, context) -> (title, content)`。模板只允许使用招聘名称、状态、站内链接，不接收简历内容与申请人完整个人信息 | service |
| service.py [A] | `notify(...)`，见下方签名 | B、C 的所有触发点 |
| mail.py [A] | `send_email_log(email_log_id)`、`retry_pending_emails(limit)`，规则见 4.9 | jobs |
| jobs.py [A] | 邮件重试命令的实现 | cron |
| views.py / serializers.py / urls.py [C] | 通知中心，见 7.5 | 前端 |

```python
def notify(
    *,
    recipient: User,
    type: str,
    recruitment: Recruitment | None,
    application: Application | None = None,
    context: dict | None = None,
) -> Notification | None:
    """必须在 atomic 内调用（assert_in_atomic）。
    - 申请相关通知必须同时给 recruitment 与 application（1.5 设计细节 3）
    - 招聘已过留存期限时不生成申请相关通知，返回 None
    - recipient.email_notify_enabled 为真时，同一事务内创建 pending 的 EmailLog
    - 用 transaction.on_commit 触发首次发送，不在事务内发邮件
    """
```

### 4.6 files（storage/validators/jobs 为 A，下载视图为 C）

```python
# apps/files/storage.py [A]
@dataclass(frozen=True)
class StoredResume:
    path: str           # 相对私有根目录的路径，写入 Application.resume_file
    original_name: str  # 清洗后的展示名，≤255，写入 resume_name
    size: int           # 写入 resume_size，≤ 10485760
    type: str           # 'pdf' | 'doc' | 'docx'，写入 resume_type

def validate_resume(upload: UploadedFile) -> None:
    """扩展名 + 文件头特征值 + 大小。不信任客户端 Content-Type。
    不通过抛 BizError('INVALID_RESUME_FILE', details={'reason': 'type'|'size'|'signature'})"""

def save_resume(upload: UploadedFile) -> StoredResume:
    """先 validate，再用随机名写入 PRIVATE_FILE_ROOT/resumes/YYYY/MM/<uuid>.<ext>，
    绝不使用用户给的文件名拼路径。必须在 atomic 之外调用。"""

@contextmanager
def staged_resume(upload) -> Iterator[StoredResume]:
    """with 块内抛任何异常都会 discard 新文件再重新抛出。B 的用法：
        with staged_resume(upload) as f:
            with transaction.atomic(): ...创建/更新申请...
        discard_resume(old_path)   # 仅替换简历时，事务提交成功后调用"""

def discard_resume(path: str) -> bool:
    """删除文件，不存在视为成功，失败只记日志并返回 False，不抛异常。"""

def open_resume(path: str) -> BinaryIO: ...

def cleanup_orphans(*, older_than: timedelta = timedelta(hours=24),
                    referenced: Callable[[list[str]], set[str]]) -> CleanupReport:
    """扫描 resumes/ 下未被任何 Application 引用且 mtime 超过 24 小时的文件并删除。
    referenced 由调用方传入，分批查询 Application.resume_file。"""
```

- `PRIVATE_FILE_ROOT` 必须在 Web 服务器静态目录与 `MEDIA_ROOT` 之外，不配置任何直链路由。
- 反向代理上传体积上限设为略大于 10MB（例如 11MB），精确的 10MB 判断由 `validate_resume` 完成。
- 替换简历时，提交成功后旧文件删除若失败，旧文件已不被任何申请引用，会被 `cleanup_orphans` 在满 24 小时后清除。因此不需要额外的“待删除文件”表。

下载视图（C）：`apps/files/views.py::download_resume(request, application_id)`
1. `peek` 取得申请与招聘（不加锁，只读）。
2. `resolve_application_access(...)`，`can_download_resume` 为假则返回 404（并记 `permission_denied`），不泄露申请是否存在。
3. 发布者下载时 `audit.record(action="resume_view", ...)`。
4. `FileResponse(open_resume(path), as_attachment=True, filename=app.resume_name)`，响应头加 `X-Content-Type-Options: nosniff`、`Cache-Control: private, no-store`。

### 4.7 chat（models 为 A，其余为 C）

| 文件 | 作用与内容 |
|------|-----------|
| models.py [A] | `ChatConversation`、`ChatMessage`，约束见第 5 章 |
| services.py [C] | `get_or_create_conversation(user, peer_uid) -> ChatConversation`（按 id 大小排成 `user_low_id < user_high_id`，不可与自己聊天）；`send_message(user, conversation_id, content)`（校验是参与者、长度 1–2000，**同一事务内**更新 `last_message_at`）；`mark_read(user, conversation_id)`（把对方发来的未读消息写 `read_at`） |
| selectors.py [C] | 会话列表（按 `last_message_at` 倒序，附未读数）、消息列表（`after_id` 增量拉取，第一版靠轮询） |
| views.py / serializers.py / urls.py [C] | 见 7.6 |

- 管理员没有任何读取聊天内容的入口，包括 `admin.py`：Django Admin 不注册这两个模型。
- 非参与者访问会话一律返回 404。

### 4.8 audit 与 retention（A）

```python
# apps/audit/service.py
def record(*, actor: User | None, action: str, target_type: str,
           target_id: int | None, reason: str | None = None) -> AuditLog:
    """actor_role / actor_is_admin 在函数内从 actor 取值快照，actor 为 None 时二者同为 None。
    不接受任何自由文本字段之外的内容；调用方不得把原始文件名、补充说明、认证凭证放进 reason。
    业务操作的审计（admin_delete、recruitment_delete、application_update、resume_view）
    在业务事务内调用，与业务同提交；权限拒绝的审计在事务外由异常处理器调用。"""
```

`action` 常量放在 `audit/actions.py`：`recruitment_delete`、`admin_delete`、`resume_view`、`application_update`、`permission_denied`。

```python
# apps/recruitments/retention.py [A]
def purge_expired_applications(recruitment_id: int, *, now: datetime | None = None) -> bool:
    """1.4 设计细节 6 的实现，返回本次是否真正执行了清理。
    1. sync_recruitment 补执行，确保没有遗留 processing（事务一）
    2. 校验 is_retention_expired 且 applications_anonymized_at 为空
    3. 删除所有关联简历文件（不存在视为成功）；任一失败则本次放弃，等下次重试
    4. 事务二：锁招聘 → 汇总五种状态数量写入 application_status_counts
       → 先删 EmailLog → 再删 Notification（application_id 指向这些申请的，
         以及 recruitment_id 指向本招聘且 type 以 'application_' 开头的）
       → 最后删全部 Application → 写 applications_anonymized_at。计数与标记同一事务。
    5. 已完成的招聘直接返回，不覆盖已有统计。"""
```

### 4.9 邮件发送的状态规则（A，mail.py）

database.md 对 `attempts` 的描述需要一个可实现的判定，规划如下（也列入 9.6）：

- 创建 EmailLog 时：`status='pending'`、`attempts=0`、`last_error=NULL`。
- 发送前先对该行 `select_for_update(skip_locked=True)`，拿不到锁说明别的任务在处理，直接跳过。
- 发送前重新检查：通知仍存在、招聘未过留存期限、状态仍为 `pending`。
- 如果 `last_error IS NOT NULL`，说明这是重试，先 `attempts += 1` 再发送；否则是首次发送，`attempts` 保持 0。
- 成功 → `sent`。失败 → 写 `last_error`；若 `attempts == 3` → `failed`，否则保持 `pending`。
- 重试时机：没有 `next_retry_at` 字段，用 `updated_at` 与退避表比较（例如 `attempts` 为 0/1/2 时分别等待 1/5/30 分钟）。
- 连续失败触发告警：`failed` 状态出现时写 ERROR 级日志，运维按日志告警。

## 5 数据表约束与 database.md 的对应

所有表由 A 在对应 app 的 `models.py` 里声明，`db_table` 显式指定。约束名与 database.md 保持一致，便于对照。

| database.md | Django 模型 / `db_table` | 约束与索引（`Meta.constraints` / `indexes`） |
|-------------|--------------------------|----------------------------------------------|
| 1.1 | accounts.User / `app_user` | `UniqueConstraint(Lower("email"), name="user_email_lower_uniq")`；`CheckConstraint(~Q(password="") \| Q(sso_subject__isnull=False), name="user_login_method_chk")`；`role` 的 CHECK；`uid`、`real_id` UNIQUE；`sso_subject` UNIQUE 可空 |
| 1.2 | recruitments.Recruitment / `recruitment` | `recruitment_full_chk`、`recruitment_closed_time_chk`、`recruitment_full_time_chk`、`recruitment_close_pair_chk`、`recruitment_cleanup_pair_chk`；`type`/`status`/`close_reason` 的 CHECK；人数范围 CHECK（`1<=max_headcount`、`min_headcount` 为空或在 `[1,max]`、`0<=accepted_count<=max_headcount`）；5 个部分索引（同名）；`pg_trgm` 的 GIN 索引在独立迁移里启用 `TrigramExtension` 后创建 |
| 1.3 | recruitments.Tag / `tag`；RecruitmentTag / `recruitment_tag` | `Tag.name` UNIQUE；`UniqueConstraint(["recruitment","tag"])`；显式 `through` 模型，不用默认中间表，以便表名与 database.md 一致 |
| 1.4 | applications.Application / `application` | `application_decided_chk`；`UniqueConstraint(["recruitment","applicant"], condition=~Q(status="withdrawn"), name="application_active_uniq")`；`resume_size <= 10485760`、`resume_type`、`status`、`publisher_mark` 的 CHECK；两个普通索引（同名） |
| 1.5 | notifications.Notification / `notification` | 索引 `(recipient, is_read, -created_at)`；`type` 不加 CHECK（见 0 第 3 条例外） |
| 1.6 | notifications.EmailLog / `email_log` | `status` 的 CHECK；`0 <= attempts <= 3` 的 CHECK |
| 1.7 | chat.ChatConversation / `chat_conversation`；ChatMessage / `chat_message` | `CheckConstraint(Q(user_low__lt=F("user_high")))`；`UniqueConstraint(["user_low","user_high"])`；索引 `(conversation, created_at)` |
| 1.8 | audit.AuditLog / `audit_log` | 操作者三字段成对为空的 CHECK（v0.3 新增）；索引 `(target_type, target_id)`、`(actor, -created_at)`；`action` 不加 CHECK |

通用转化规则：
- 所有外键显式 `on_delete=models.PROTECT`（0 第 4 条）。
- 枚举字段用 `TextChoices` + `CheckConstraint`，取值来自 `core/choices.py`，不重复手写字符串。
- `created_at`、`status` 默认值等用 `db_default`，使绕过 ORM 的写入也满足 NOT NULL；`updated_at` 用 `auto_now`，批量 `update()` 必须显式带上。
- 上述 CHECK 在 Django 里用 `Q` 表达。成对为空的写法例如：`(Q(a__isnull=True) & Q(b__isnull=True)) | (Q(a__isnull=False) & Q(b__isnull=False))`。
- 迁移完成后，A 用 `\d+ <table>` 对照 database.md 逐表核对一次，并把核对结果写进迁移的评审记录。

## 6 接口约定

### 6.1 统一信封

所有接口（含错误）返回 JSON：

```json
{ "code": "OK", "message": "", "data": { }, "request_id": "..." }
```

- 成功：HTTP 2xx，`code="OK"`。
- 失败：HTTP 4xx/5xx，`code` 为业务错误码，`message` 为可直接展示的中文提示，`data` 为 `null` 或 `{"details": {...}}`（字段级校验错误放这里）。
- 列表：`data = {"items": [...], "page": 1, "page_size": 20, "total": 134}`。
- 文件下载成功时返回文件流，失败仍返回上述信封。

### 6.2 命名与格式规律

- 前缀 `/api/v1/`；资源用复数名词，URL 全小写、单词用短横线；JSON 字段 snake_case。
- 读取：`GET /<资源>`、`GET /<资源>/{id}`；创建：`POST /<资源>`；局部修改：`PATCH /<资源>/{id}`；删除：`DELETE /<资源>/{id}`。
- 状态流转一律 `POST /<资源>/{id}/<动词>`，动词小写单个词：`close`、`withdraw`、`accept`、`reject`、`hold`、`unhold`、`read`。
- “我的”资源放在 `/me/` 下：`/me/recruitments`、`/me/applications`。
- 用户对外只用 `uid`（32 位 hex），不暴露 `id` 与 `real_id`。招聘、申请、通知、会话用数字 `id`，访问权限靠对象级校验。
- 时间字段：ISO 8601 带偏移；金额类无。布尔字段 `is_` 开头，时间字段 `_at` 结尾。
- 招聘对外状态：`open | full | closed`，另给布尔 `is_deleted`。申请对外状态：`processing | accepted | rejected | withdrawn | invalid`，发布者另可见 `publisher_mark: none | hold`。
- 无权访问他人的申请、会话一律返回 404；对象可见但操作不被允许返回 403。

### 6.3 错误码

| code | HTTP | 含义 |
|------|------|------|
| OK | 200/201 | 成功 |
| UNAUTHENTICATED | 401 | 未登录或会话失效 |
| FORBIDDEN | 403 | 对象可见，但无权执行该操作 |
| NOT_FOUND | 404 | 对象不存在或不可见 |
| VALIDATION_ERROR | 400 | 参数校验失败，`details` 带字段错误 |
| PRIVACY_NOT_CONSENTED | 403 | 未确认个人信息处理告知，不能提交申请 |
| SELF_APPLICATION_FORBIDDEN | 403 | 不能申请自己发布的招聘 |
| RECRUITMENT_NOT_OPEN | 409 | 招聘已删除/已满员/已关闭/已过截止，不能投递 |
| RECRUITMENT_NOT_EDITABLE | 409 | 招聘当前状态不允许修改/删除/关闭 |
| RECRUITMENT_FULL | 409 | 接受时已满员 |
| PROCESSING_WINDOW_CLOSED | 409 | 关闭已满 7 天，发布者不能再处理 |
| HEADCOUNT_BELOW_ACCEPTED | 409 | 人数上限不得小于已接受人数 |
| DUPLICATE_APPLICATION | 409 | 已有未撤回的申请 |
| APPLICATION_NOT_PROCESSING | 409 | 申请已不是处理中 |
| INVALID_RESUME_FILE | 400 | 文件格式/大小/特征不符，`details.reason` 区分 |
| AUTH_FAILED | 401 | 统一身份认证失败或必要信息缺失 |
| SSO_UNAVAILABLE | 503 | 统一身份认证服务暂时不可用 |
| INTERNAL_ERROR | 500 | 未预期错误，不暴露内部细节 |

### 6.4 鉴权与跨站

- 会话 cookie：`HttpOnly`、`Secure`、`SameSite=Lax`；全站 HTTPS。
- 写接口走 DRF `SessionAuthentication`，强制 CSRF；前端先 `GET /auth/csrf`，之后在请求头带 `X-CSRFToken`。
- 默认所有接口需要登录，公开接口（登录、回调、健康检查）显式声明。
- 认证凭证（SSO ticket、会话 key）不写日志、不落库。

## 7 接口清单

“实现者”是写这个 view 的人；“底层依赖”是它调用的本文第 4 章接口。

### 7.1 认证与个人资料（A）

| 方法 路径 | 作用 | 权限 | 底层依赖 |
|-----------|------|------|---------|
| GET `/auth/sso/login` | 跳转统一身份认证 | 公开 | sso |
| GET `/auth/sso/callback` | 回调，建会话 | 公开 | sso、accounts.services |
| POST `/auth/logout` | 登出 | 登录 | — |
| GET `/auth/csrf` | 下发 CSRF token | 公开 | — |
| POST `/auth/dev-login` | 开发期登录，生产禁用 | 公开，仅开发环境 | accounts.services |
| GET `/me` | 当前用户：`uid, nickname, role, is_admin, email, email_notify_enabled, privacy_consented` | 登录 | — |
| PATCH `/me` | 改昵称、邮件开关 | 登录 | accounts.services |
| POST `/me/privacy-consent` | 确认个人信息处理告知 | 登录 | accounts.services |
| GET `/healthz` | 健康检查 | 公开 | core.health |

### 7.2 用户与标签（B 实现展示，A 提供数据）

| 方法 路径 | 作用 | 权限 |
|-----------|------|------|
| GET `/users/{uid}` | 个人主页公开信息：`uid, nickname, role` | 登录 |
| GET `/users/{uid}/recruitments` | 该用户已发布且未删除的招聘 | 登录 |
| GET `/tags` | 可用领域标签（`is_active`），按 `sort_order` | 登录 |

### 7.3 招聘（B）

| 方法 路径 | 作用 | 权限 | 底层依赖 |
|-----------|------|------|---------|
| GET `/recruitments` | 列表/搜索：`q, type, tag, status, page, page_size`；不含已删除 | 登录 | selectors |
| POST `/recruitments` | 发布，至少一个 tag，截止时间须晚于当前且不超过一年 | 登录 | services |
| GET `/recruitments/{id}` | 详情，含当前用户是否已申请、发布者可见的申请统计 | 登录 | selectors、rules |
| PATCH `/recruitments/{id}` | 修改（仅 open 且未过截止），可上调/下调人数上限但不得小于已接受人数 | 发布者 | state.run_in_recruitment_tx、policies |
| POST `/recruitments/{id}/close` | 手动关闭 | 发布者 | 同上 |
| DELETE `/recruitments/{id}` | 删除；JSON body `{"reason": "..."}`，管理员删除时必填 | 发布者或管理员 | 同上、audit、notifications |
| GET `/me/recruitments` | 我发布的招聘（含已关闭/已满员，不含已删除） | 登录 | selectors |

### 7.4 申请（B）

| 方法 路径 | 作用 | 权限 | 底层依赖 |
|-----------|------|------|---------|
| POST `/recruitments/{id}/applications` | 提交申请，`multipart/form-data`：`resume`（文件）、`note`（可空） | 登录 | files.staged_resume、state、policies |
| GET `/recruitments/{id}/applications` | 发布者查看该招聘的申请，可按 `status` 筛选 | 发布者 | policies、selectors |
| GET `/me/applications` | 我发出的申请 | 登录 | selectors |
| GET `/applications/{id}` | 申请详情；发布者查看时清除 `has_unseen_update` | 申请人或发布者 | policies.resolve_application_access |
| PATCH `/applications/{id}` | 申请人改 `note` 或替换 `resume` | 申请人 | files、state、audit |
| POST `/applications/{id}/withdraw` | 撤回 | 申请人 | state |
| POST `/applications/{id}/accept` | 接受 | 发布者 | state.mark_full、notifications |
| POST `/applications/{id}/reject` | 拒绝 | 发布者 | notifications |
| POST `/applications/{id}/hold` | 暂留（私有标记，状态仍为 processing） | 发布者 | — |
| POST `/applications/{id}/unhold` | 取消暂留 | 发布者 | — |

### 7.5 简历下载与通知（C）

| 方法 路径 | 作用 | 权限 | 底层依赖 |
|-----------|------|------|---------|
| GET `/applications/{id}/resume` | 下载简历 | 按 `can_download_resume` | policies、files.open_resume、audit |
| GET `/notifications` | 我的通知，`is_read`、分页 | 登录 | models |
| GET `/notifications/unread-count` | 未读数 | 登录 | models |
| POST `/notifications/{id}/read` | 标记已读 | 接收人 | models |
| POST `/notifications/read-all` | 全部已读 | 登录 | models |

### 7.6 聊天与推荐（C）

| 方法 路径 | 作用 | 权限 |
|-----------|------|------|
| GET `/chat/conversations` | 会话列表，带未读数，按最近消息倒序 | 登录 |
| POST `/chat/conversations` | body `{"peer_uid": "..."}`，获取或创建与某人的会话 | 登录 |
| GET `/chat/conversations/{id}/messages` | 消息列表，支持 `after_id` 增量拉取 | 参与者 |
| POST `/chat/conversations/{id}/messages` | 发送文本（1–2000 字） | 参与者 |
| POST `/chat/conversations/{id}/read` | 对方消息标记已读 | 参与者 |
| GET `/feed/recruitments` | 招聘推送；第一版等价于按发布时间倒序的列表，响应结构与 `/recruitments` 完全相同，后续换成个性化排序时前端无需改动 | 登录 |

### 7.7 底层接口使用方一览

| 底层接口 | B | C | 定时任务 |
|----------|---|---|---------|
| `run_in_recruitment_tx` | ✓ | | |
| `sync_recruitment` | 间接 | | ✓ |
| `mark_full` / `reject_processing_applications` | ✓ | | 间接 |
| `rules.*` | ✓ | ✓ | ✓ |
| `policies.resolve_application_access` 等 | ✓ | ✓ | |
| `notify` | ✓ | | ✓（自动拒绝） |
| `files.staged_resume` / `discard_resume` | ✓ | | |
| `files.open_resume` | | ✓ | |
| `audit.record` | ✓ | ✓ | |
| `core.errors` / `responses` | ✓ | ✓ | |

## 8 定时任务

均为 management command，由 cron 每分钟（清理类每小时）调用，命令内部对每个招聘单独开事务，一条失败不影响其他条。

| 命令 | 作用 | 扫描条件 |
|------|------|---------|
| `run_sync_recruitments` | 到期关闭、七天自动拒绝 | `status='open' AND deleted_at IS NULL AND deadline <= now`；`status='closed' AND deleted_at IS NULL AND closed_at <= now-7d AND EXISTS(processing 申请)`。逐个调用 `sync_recruitment` |
| `run_purge_applications` | 180 天申请明细清理 | `applications_anonymized_at IS NULL` 且 `LEAST(closed_at, full_at, deleted_at) <= now-180d`（`LEAST` 忽略 NULL）。逐个调用 `purge_expired_applications` |
| `run_send_emails` | 邮件首次发送兜底与重试 | `status='pending'`，按 4.9 |
| `run_cleanup_orphan_files` | 孤立简历文件 | 未被引用且 mtime 超过 24 小时 |
| `run_cleanup_audit_logs` | 审计日志留存 | 仅删除 `created_at` 满一年的记录（见 9.6） |

接口不依赖这些任务及时运行：所有写接口都经 `run_in_recruitment_tx` 先补执行。

## 9 需要 A 定夺的事项，以及 database.md 转化时的出入

### 9.1 需要定夺

1. **接口框架**：是否引入 DRF（需要在环境手册的依赖里加一项）。我建议用：PATCH 带 multipart、序列化校验、CSRF 都要自己补，手写成本更高。不用 DRF 的话第 6、7 章里的 PATCH multipart 需要改成 POST。
2. **定时任务**：cron + management command（零额外组件）还是 Celery beat（需要 Redis/消息队列）。数据规模是 2000 条招聘、单条 200 份申请，我建议前者。
3. **会话方式**：session cookie + CSRF（我建议）还是 token。选 token 的话 6.4 要重写，且 cookie 相关安全要求不再适用。
4. **申请上传方式**：我写成一步到位的 multipart（文件随申请一起提交），C 只做下载与权限。若你想让 C 另做独立的“先上传、后提交”接口，需要增加带签名、带过期时间的文件令牌，攻击面和状态都更多，不建议。
5. **状态机共享代码归属**：我把 `sync_recruitment`、`mark_full`、`run_in_recruitment_tx` 和 180 天清理都划给了 A，因为它们是并发正确性的核心，B 只调用。如果你希望交给 B，需要你把签名冻结后再放手。
6. **用户字段的可见范围**：我默认对外只暴露 `uid, nickname, role`，发布者看申请时额外可见申请人的 `name`，`email` 与 `real_id` 只在 `/me` 返回自己的。需要确认发布者是否能看到申请人真实姓名。
7. **角色判定与邮箱规则**：1.1 写“依据学号/工号判定”，但没有规则（例如学号位数、前缀），“同济邮箱格式”也没有域名白名单。`identity.py` 需要这两个规则才能写完。
8. **人数上限的“待定值”**：需求写“＜待定值”，database.md 只有 `>= 1`。需要一个应用层常量作为 `max_headcount` 的上限。
9. **已删除招聘对相关人的可见性**：database.md 规定已删除招聘“不在任何列表出现”。但申请被置为 `invalid` 后，申请人在“我的申请”里仍需要显示招聘名称。我默认：`/me/applications` 的每条记录内嵌 `recruitment: {id, title, status, is_deleted}`，不提供已删除招聘的详情接口。需要确认。
10. **列表默认排序**：需求希望进行中在前、已关闭/已满员在后，但索引 `(status, created_at DESC)` 只支持按单一状态筛选后按时间排序。我默认实现为“按 `status` 分组权重 + 发布时间倒序”，数据量下不需要新索引；若你想改成只按时间排序则更简单。
11. **`resume_view` 审计的时机**：1.8 写“发布者查看申请人简历”。我默认在**下载**时记录，查看申请详情（只返回文件元数据）不记。需要确认。

### 9.2 与 database.md 在转化中产生的出入

这些我没有改动 database.md，需要你决定是否同步修改设计。

1. **`is_staff` 缺失，Django 自带的权限表会多出来**：1.1 说 `is_staff` / `is_superuser` 仅用于 Django Admin，但 1.1 的表里没有 `is_staff` 列。继承 `PermissionsMixin` 还会多出 `is_superuser` 列以及 `app_user_groups`、`app_user_user_permissions` 两张表，第 2 章概览里也没有它们。
   - 选项一：在 1.1 补 `is_staff` 列，并在第 2 章注明这两张自带表。
   - 选项二：不继承 `PermissionsMixin`，自己加 `is_staff`、`is_superuser`，少两张表，但要自己处理 Admin 权限检查。
   - Tag 的维护依赖 Django Admin，所以这个问题不能忽略。
2. **`password` 默认值**：`AbstractBaseUser.password` 默认没有 `DEFAULT ''`，模型里需要覆盖该字段，才能与 1.1 的 `NOT NULL DEFAULT ''` 对应。
3. **`updated_at` 与批量更新**：`auto_now` 只在 `save()` 时生效。自动拒绝、删除置失效等批量 `update()` 需要显式写 `updated_at`，已在 4.3 的 `reject_processing_applications` 里要求。
4. **外键 PROTECT 是 Django 层的**：数据库里实际是默认的 `NO ACTION`，行为等价（都会阻止删除），仅提醒一下。
5. **外键自带索引**：Django 会给每个外键自动建索引，因此实际索引比 database.md 列出的多（例如 `application.recruitment_id`、`email_log.notification_id`）。这对清理时按外键查找有利，我默认接受，不逐个关闭。
6. **`attempts` 的判定**：1.6 写“首次为 0，重试前加 1”，但没说明如何区分“从未发送”和“已发送失败过一次”（二者都是 `pending` 且 `attempts=0`）。我用 `last_error IS NULL` 区分（见 4.9），并用 `updated_at` 加退避表决定重试时机，因为表里没有 `next_retry_at`。
7. **“专用暂存前缀目录”的理解**：1.4 设计细节 5 的说法容易理解成“先写暂存目录、提交后再搬到正式目录”。搬动会引入“数据库已指向新路径、文件还没搬”的窗口。我的实现是文件一次写入最终路径，整个 `resumes/` 目录就是清理扫描的范围，不做搬动。
8. **旧文件删除失败的重试**：不增加“待删除文件”表，靠孤立文件清理兜底（最长约 24 小时），见 4.6。
9. **审计日志留存清理任务**：1.8 要求日志满一年后可由后台任务清理，但 0 第 6 条的定时任务清单里没有列它。我在第 8 章加了 `run_cleanup_audit_logs`，建议在 0 第 6 条补一行。
10. **`Notification.type` 的约束只在应用层**：清理逻辑依赖 `application_` 前缀（1.4 设计细节 6）。因为数据库不校验，我在 `notifications/types.py` 集中定义，并用一条单元测试保证所有申请事件类型都带该前缀。
11. **谁删除、为什么删除没有落在招聘表上**：`Recruitment` 只有 `deleted_at`，不记录是发布者还是管理员删的，原因也只在 `AuditLog.reason` 里。如果前端需要显示“被管理员删除”，只能通过通知或审计查询，接口层面不会提供。
12. **`has_unseen_update` 的清除**：1.4 写“发布者查看后置为 FALSE”。我实现在 `GET /applications/{id}` 里（带副作用的读），而不是单独的“标记已看”接口。如果你更想要显式接口，需要增加一条路由。

## 10 建议的交付顺序（A）

让 B、C 尽早能并行开工：

1. **里程碑一**（B、C 的前置）：项目骨架、`settings`、`core`（信封、错误、分页、时钟、tx）、全部 `models.py` 与迁移、`dev-login`、`/me`、测试基类与工厂。
2. **里程碑二**：`rules.py`、`policies.py`、`state.py`（含 `sync_recruitment`、`mark_full`、`run_in_recruitment_tx`）、`files/storage.py`、`notify`、`audit.record`。到此 B 可完整实现招聘与申请，C 可实现通知中心与聊天。
3. **里程碑三**：`mail.py` 与邮件重试、`retention.py`、全部定时命令、孤立文件清理、SSO 正式实现、`/healthz`。
4. **里程碑四**：并发与补执行的 `TransactionTestCase` 用例（重复接受、接受与撤回冲突、超员、任务延迟）、审计与权限拒绝路径用例。
