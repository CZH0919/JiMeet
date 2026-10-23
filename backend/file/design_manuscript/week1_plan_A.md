# A 的第一周实施

范围：只做 A 的工作，即后端规则 + 公共底层 + 数据库与应用层之间的 Python 接口。
依据：[database.md](database.md)（设计，不改）、[implementation_plan.md](implementation_plan.md)（总体规划）。本文与总规划冲突时，以本文为准。
不做：招聘/申请的 services、selectors、serializers、views（B）；简历下载视图、通知中心、聊天、推送（C）。这些只预留位置。

## 0 已拍板的决定

| # | 事项 | 决定 |
|---|------|------|
| 1 | A 的边界 | 骨架、`core`、全部 models 与迁移、`accounts`、`rules`、`policies`、`state`、`notify`、`audit`、`files/storage`、测试基类与契约测试 |
| 2 | `is_staff` | 加进 `User`，继承 `AbstractBaseUser` + `PermissionsMixin`，接受多出的 `is_superuser` 列和 `app_user_groups`、`app_user_user_permissions` 两张表 |
| 3 | 截止时间 / 人数校验 | 数据库层不做；A 在 `rules.py` 提供 `validate_deadline`、`validate_headcount`，应用层（B）调用 |
| 4 | 提交申请的通知 | 发给发布者，类型 `application_submitted`，同时带 `recruitment_id` 与 `application_id`。申请被接受/拒绝/撤回/修改的通知沿用 database.md 1.5 已列类型 |
| 5 | `max_headcount` 上限 | 50，常量 `MAX_HEADCOUNT_LIMIT = 50` 放 `settings/base.py` |
| 6 | 本周业务 | 发布招聘、状态流转（含截止/满员/七天窗口）、申请加入、申请处理（接受/拒绝/暂留）。修改招聘、手动关闭、删除招聘、撤回/修改申请：本周只保证底层够用，不排接口任务 |
| 7 | 发布者可见申请人姓名 | 可见。`ApplicationAccess` 增加 `can_see_applicant_name` |
| 8 | 接口框架 / 会话 / 定时 | DRF + session cookie + CSRF + management command（沿用总规划默认） |
| 9 | DRF 版本 | 先在你的环境里装并跑 `manage.py check`，确认兼容 Django 6.1 后再固定版本；不兼容就停下来找你（见 1.2） |
| 10 | 学号/工号判定 | 规则未给。开发期用临时规则：`real_id` 以 `t`/`T` 开头为教师，否则为学生；`identity.py` 里标 `TODO(规则待定)`，不得带入生产 |
| 11 | 同济邮箱 | `ALLOWED_EMAIL_DOMAINS = ["tongji.edu.cn"]`，放 settings，标注"待确认" |
| 12 | 审计拒绝记录的目标 | `BizError` 可带 `audit_target=(type, id)`；没带时 `target_type="request"`、`target_id=None`，`actor` 取不到（未登录）时为 None |
| 13 | 邮件 | 本周只创建 `EmailLog(pending)`，`on_commit` 调用 `mail.dispatch()`，该函数本周是只记日志的空实现，不真实发送 |
| 14 | 测试框架 | 用 Django 自带 runner，不引入 pytest、freezegun。时间冻结用 `core.clock.freeze()` |

需要你自己决定是否同步到 database.md 的三处（我不会改）：
- 1.1 补 `is_staff` 行，并在第 2 章注明 Django 自带的两张关联表。
- 1.1 的 `password` 在模型里覆盖为 `NOT NULL DEFAULT ''`，无需改文档，仅提醒。
- 0 第 6 条定时任务清单补"审计日志满一年清理"。

## 1 第 0 天：环境（你手工执行，约 30 分钟）

### 1.1 数据库角色

环境手册建的角色 `jimeet` 不能建库，而 `TransactionTestCase` 要建 `test_jimeet`：

```bash
psql -d postgres -c "ALTER ROLE jimeet CREATEDB;"
```

确认 `pg_trgm` 可用（招聘搜索索引需要）：

```bash
PGPASSWORD=jimeet psql -h 127.0.0.1 -U jimeet -d jimeet -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

若报权限不足，改用超级用户执行同一句，之后迁移里的 `TrigramExtension` 会因已存在而跳过。

### 1.2 Python 环境与依赖

按 [django-env-setup.md](../../../file/django-env-setup.md) 建 `backend/.venv`（Python 3.12），然后：

```bash
pip install "Django>=6.1,<6.2" "psycopg[binary]>=3.3,<4" djangorestframework
python -c "import django, rest_framework; print(django.get_version(), rest_framework.VERSION)"
```

通过 1.3 搭好骨架后再跑一次 `python manage.py check`，无警告才算兼容。兼容后用 `pip freeze` 把这三项的实际版本写成 `==` 固定到 `backend/requirements/base.txt`。若 `check` 报 DRF 与 Django 不兼容，停止并告知，不要自行换框架。

### 1.3 仓库忽略项

在仓库根 `.gitignore` 追加（若没有就新建）：`backend/.venv/`、`backend/var/`、`.env`、`__pycache__/`。

## 2 第 1 天：骨架 + core

### 2.1 创建项目

```bash
cd backend
django-admin startproject config .
mkdir -p apps tests requirements var/private
# 每个 app：
for a in core accounts recruitments applications notifications files chat audit; do
  mkdir -p apps/$a && python manage.py startapp $a apps/$a
done
touch apps/__init__.py tests/__init__.py
```

每个 `apps/<x>/apps.py` 设置 `name = "apps.<x>"`、`label = "<x>"`，`default_auto_field = "django.db.models.BigAutoField"`。

把 `config/settings.py` 拆成 `config/settings/{__init__,base,dev,prod,test}.py`，`manage.py`/`wsgi.py`/`asgi.py` 默认指向 `config.settings.dev`。

### 2.2 settings/base.py 要点（逐条落实）

- `INSTALLED_APPS`：`django.contrib.{admin,auth,contenttypes,sessions,messages}`、`django.contrib.postgres`（给 `TrigramExtension`/`GinIndex`）、`rest_framework`、八个 `apps.*`。不装 `staticfiles` 之外的多余项。
- `AUTH_USER_MODEL = "accounts.User"`。
- `DATABASES`：全部读环境变量，开发默认值 `jimeet/jimeet@127.0.0.1:5432/jimeet`，生产无默认（缺失则启动报错）。
- `TIME_ZONE = "Asia/Shanghai"`，`USE_TZ = True`，`ATOMIC_REQUESTS = False`（显式写出，不依赖默认）。
- `PRIVATE_FILE_ROOT = BASE_DIR / "var" / "private"`（可被环境变量覆盖），不在 `MEDIA_ROOT`/静态目录内；不配置任何指向它的 URL。
- `MAX_HEADCOUNT_LIMIT = 50`，`ALLOWED_EMAIL_DOMAINS`，`ALLOW_DEV_LOGIN`（默认 False）。
- 会话 cookie：`SESSION_COOKIE_HTTPONLY=True`、`SESSION_COOKIE_SAMESITE="Lax"`、`SESSION_COOKIE_SECURE`（prod 为 True，dev 为 False）、`CSRF_COOKIE_SECURE` 同。
- `REST_FRAMEWORK`：`DEFAULT_AUTHENTICATION_CLASSES=[SessionAuthentication]`、`DEFAULT_PERMISSION_CLASSES=[core.permissions.IsAuthenticatedBiz]`、`EXCEPTION_HANDLER="apps.core.exception_handler.handle"`、`DEFAULT_RENDERER_CLASSES=[JSONRenderer]`、`DEFAULT_PAGINATION_CLASS=None`（分页由 `core.pagination` 手动调用）。
- `MIDDLEWARE` 加 `apps.core.middleware.RequestIdMiddleware`（放最前）。
- `LOGGING`：控制台，格式含 `request_id`；不记录 cookie、`Authorization`、请求体。
- `settings/prod.py`：`DEBUG=False`，断言 `ALLOW_DEV_LOGIN is False`，缺 `SECRET_KEY`/数据库变量直接抛错。
- `settings/test.py`：继承 dev；`PASSWORD_HASHERS` 换成 `MD5PasswordHasher`；`PRIVATE_FILE_ROOT` 指向临时目录。
- `.env.example` 列出全部变量名，不写真实值。

### 2.3 core 逐文件实现

按下面顺序写，每个文件写完立刻写对应单元测试。

1. `core/choices.py`：八个 `TextChoices`，取值与 database.md 的 CHECK 完全一致（`Role`: student/teacher；`RecruitmentType`: competition/activity/internship；`RecruitmentStatus`: open/full/closed；`CloseReason`: deadline/manual；`ApplicationStatus`: processing/accepted/rejected/withdrawn/invalid；`PublisherMark`: none/hold；`ResumeType`: pdf/doc/docx；`EmailStatus`: pending/sent/failed）。
2. `core/clock.py`：`now()`、`freeze(dt)`（上下文管理器，只用于测试，内部用模块级变量覆盖，退出还原）。
3. `core/errors.py`：`BizError(code, http_status, message, details=None, audit_target=None)`，子类固定 code 与 status：`NotAuthenticated`(UNAUTHENTICATED/401)、`Forbidden`(FORBIDDEN/403)、`NotFound`(NOT_FOUND/404)、`ValidationFailed`(VALIDATION_ERROR/400)、`Conflict`（code 由调用方给，status 409）、`NotFoundAsDenied`(NOT_FOUND/404，handler 会记 `permission_denied`)。错误码常量集中成 `class ErrorCode`，覆盖总规划 6.3 的全部码。
4. `core/responses.py`：`ok(data=None)`、`created(data)`、`page(items, page, page_size, total)`，输出 `{code, message, data, request_id}`。
5. `core/exception_handler.py`：`handle(exc, context)`
   - `BizError` → 信封。
   - DRF 自带异常（`NotAuthenticated`、`PermissionDenied`、`ValidationError`、`Http404`、`MethodNotAllowed`、`ParseError`）→ 映射到同名错误码。
   - 其他异常 → `INTERNAL_ERROR`，响应不含堆栈；日志记录堆栈。
   - 拒绝类（`Forbidden`、`NotAuthenticated`、`NotFoundAsDenied`）→ 调 `audit.service.record(action="permission_denied", ...)`，包在 `try/except` 里，记录失败只写日志，不改变响应。
6. `core/pagination.py`：`paginate(queryset, request) -> (items, page, page_size, total)`；`page` 默认 1，`page_size` 默认 20、最大 50，非法值抛 `ValidationFailed`。
7. `core/permissions.py`：`IsAuthenticatedBiz`（未登录抛 `NotAuthenticated`）、`IsAdminFlag`（只看 `user.is_admin`）。
8. `core/tx.py`：
   ```python
   def assert_not_in_atomic() -> None   # connection.in_atomic_block 为真则抛 RuntimeError
   def assert_in_atomic() -> None       # 为假则抛 RuntimeError
   def lock_recruitment(recruitment_id: int) -> Recruitment      # select_for_update().get；不存在抛 NotFound
   def lock_application(application_id: int, recruitment: Recruitment) -> Application
        # 校验 application.recruitment_id == recruitment.id，且已持有该招聘锁；否则抛 RuntimeError
   def peek_application_recruitment_id(application_id: int) -> int   # 只读 values_list，不加锁
   ```
9. `core/middleware.py`：从请求头 `X-Request-Id` 取值（限长 64、仅字母数字短横线，否则忽略）或生成 uuid4 hex，挂到 `request.request_id` 与日志上下文，写回响应头。
10. `core/health.py`：`GET /healthz` 执行 `SELECT 1`，成功 200，失败 503；不要求登录。
11. `config/urls.py`：`/api/v1/` 前缀，先只挂 `healthz`；各 app 的 `urls.py` 以后由各自实现者追加一行 `path(..., include(...))`，该文件由 A 合并。

### 2.4 测试基类

`tests/base.py`：
- `TxTestCase(TransactionTestCase)`：`reset_sequences = False`，提供 `login(user)`（DRF `APIClient.force_login`）、`freeze_at(dt)`。
- `tests/factories.py`：手写工厂函数（不引入 factory_boy）：`make_user(real_id=None, role="student", is_admin=False, privacy=True)`、`make_tag(name, active=True)`、`make_recruitment(publisher, **overrides)`（默认 open、max=3、deadline=now+7 天）、`make_application(recruitment, applicant, status="processing", **kw)`。工厂内部要遵守全部 CHECK，例如 status=accepted 时同时写 `decided_at`。

### 2.5 第 1 天验收

```bash
python manage.py check
python manage.py test tests.core
curl -s localhost:8000/api/v1/healthz     # runserver 后手动一次
```

全绿后提交。

## 3 第 2 天：models + 迁移

### 3.1 实现顺序与迁移依赖

`accounts` → `recruitments` → `applications` → `notifications` → `audit` → `chat`。依赖是单向的，没有环。**每建完一个 app 就执行一次 `makemigrations <app>` 并 `migrate`**，不要攒到最后。

先在 `accounts` 建模并迁移，再做其余。`AUTH_USER_MODEL` 必须在第一次 `migrate` 前就指向 `accounts.User`，否则要清库重来。

### 3.2 通用写法

- 所有外键 `on_delete=models.PROTECT`，`related_name` 显式写。
- 时间字段 `created_at = DateTimeField(db_default=Now())`；`updated_at = DateTimeField(auto_now=True)`。
- 带 `default` 的 NOT NULL 字段同时写 `db_default`。
- 每个模型 `Meta.db_table` 显式，约束名与 database.md 逐字一致。
- 枚举字段：`CharField(max_length=..., choices=X.choices)` + `CheckConstraint(condition=Q(field__in=X.values), name="<table>_<field>_chk")`。
- 每个模型写 `__str__` 只含 id，不含个人信息。

### 3.3 逐表要点（字段以 database.md 为准，这里只写易错处）

**accounts.User**（`app_user`）
- `class User(AbstractBaseUser, PermissionsMixin)`；新增 `is_staff = BooleanField(db_default=False)`；`is_superuser` 由 mixin 提供。
- `uid = CharField(32, unique=True, default=lambda: uuid4().hex)`（用具名函数，迁移要可序列化）。
- 覆盖 `password = CharField(128, default="", db_default="")`。
- `USERNAME_FIELD = "real_id"`；`REQUIRED_FIELDS = ["name", "email", "nickname"]`；自定义 `UserManager` 的 `create_user`/`create_superuser`。
- 约束：`UniqueConstraint(Lower("email"), name="user_email_lower_uniq")`；`CheckConstraint(condition=~Q(password="") | Q(sso_subject__isnull=False), name="user_login_method_chk")`。
- `sso_subject` 可空唯一；`last_login` 由基类提供。

**recruitments.Recruitment**（`recruitment`）
- 五个表级 CHECK，写法：
  ```python
  CheckConstraint(condition=Q(accepted_count__lt=F("max_headcount")) | Q(status="full"), name="recruitment_full_chk")
  CheckConstraint(condition=~Q(status="closed") | Q(closed_at__isnull=False), name="recruitment_closed_time_chk")
  CheckConstraint(condition=~Q(status="full") | Q(full_at__isnull=False), name="recruitment_full_time_chk")
  CheckConstraint(condition=(Q(closed_at__isnull=True, close_reason__isnull=True) | Q(closed_at__isnull=False, close_reason__isnull=False)), name="recruitment_close_pair_chk")
  CheckConstraint(condition=(Q(applications_anonymized_at__isnull=True, application_status_counts__isnull=True) | Q(applications_anonymized_at__isnull=False, application_status_counts__isnull=False)), name="recruitment_cleanup_pair_chk")
  ```
- 范围 CHECK：`max_headcount__gte=1`；`min_headcount` 为空或 `1 <= min <= max`；`0 <= accepted_count <= max_headcount`。**数据库层不设 50 上限**（上限在应用层，见 4.1）。
- 五个部分索引（名称同 database.md）：`Index(fields=[...], condition=Q(...), name=...)`。`status, -created_at` 那条 `fields=["status", "-created_at"]`。
- 搜索：独立迁移，先 `TrigramExtension()`，再 `GinIndex(fields=["title"], opclasses=["gin_trgm_ops"], name="recruitment_title_trgm")` 与 description 同理。
- `Tag`（`tag`）、`RecruitmentTag`（`recruitment_tag`）：显式 through，`UniqueConstraint(["recruitment","tag"])`。

**applications.Application**（`application`）
- `resume_size = PositiveIntegerField` + CHECK `<= 10485760`。
- `application_decided_chk`：`(Q(status="processing") & Q(decided_at__isnull=True)) | (~Q(status="processing") & Q(decided_at__isnull=False))`。
- 部分唯一约束 `application_active_uniq`：`UniqueConstraint(fields=["recruitment","applicant"], condition=~Q(status="withdrawn"), name=...)`。
- 两个普通索引按 database.md。

**notifications.Notification / EmailLog**（`notification` / `email_log`）
- `Notification.type` 不加 CHECK；索引 `(recipient, is_read, -created_at)`。
- `EmailLog`：`status` CHECK；`attempts` CHECK `0..3`。

**audit.AuditLog**（`audit_log`）
- `actor`、`target_id` 可空；`actor_role`、`actor_is_admin` 可空；成对为空 CHECK 名 `audit_actor_triple_chk`；索引两条。
- 模型层禁止修改与删除：`save()` 只允许新建，`delete()` 抛异常；留存清理命令（预留）用 `QuerySet._raw_delete` 之外的受控入口，本周不实现。

**chat.ChatConversation / ChatMessage**（`chat_conversation` / `chat_message`）
- `user_low`、`user_high` 的 CHECK `user_low < user_high` 与 `UniqueConstraint`；`ChatMessage` 索引 `(conversation, created_at)`。
- 不在 `admin.py` 注册。

### 3.4 预设 Tag

`apps/recruitments/seed.py` 放列表，`python manage.py seed_tags`（幂等，按 name `update_or_create`，只写入 `name`/`sort_order`/`is_active=True`，不会重新启用你手工停用的 Tag）：

计算机、软件工程、人工智能、电子信息、自动化与控制、机械、土木建筑、设计创意、交通运输、环境科学、材料、数学统计、经济管理、医学生命、人文社科、外语、艺术传媒、创新创业、其他。

后续增删走 Django Admin（`admin.py` 注册 `Tag` 与 `User`，`User` 的 `is_admin` 只在此处可改）。

### 3.5 约束测试（A 自己写）

`tests/test_constraints.py`（用 `TxTestCase`，每条断言用 `with self.assertRaises(IntegrityError), transaction.atomic():` 包住）。每个约束至少一条违反用例和一条通过用例：

| 约束 | 违反用例 |
|------|----------|
| `recruitment_full_chk` | `accepted_count == max_headcount` 且 `status='open'` |
| `recruitment_closed_time_chk` | `status='closed'`，`closed_at=None` |
| `recruitment_full_time_chk` | `status='full'`，`full_at=None` |
| `recruitment_close_pair_chk` | 只有 `closed_at` 没有 `close_reason` |
| `recruitment_cleanup_pair_chk` | 只有 `applications_anonymized_at` |
| 人数范围 | `max_headcount=0`；`min_headcount > max_headcount`；`accepted_count > max_headcount` |
| `application_decided_chk` | processing 带 `decided_at`；accepted 不带 `decided_at` |
| `application_active_uniq` | 同人同招聘两条非 withdrawn；通过：一条 withdrawn 加一条 processing |
| 简历 | `resume_size = 10485761`；`resume_type='txt'` |
| `user_login_method_chk` | `password=''` 且 `sso_subject=NULL` |
| `user_email_lower_uniq` | `A@x.com` 与 `a@x.com` |
| `email_log` | `attempts=4` |
| `audit_actor_triple_chk` | `actor_id` 为空但 `actor_role` 非空 |
| chat | `user_low >= user_high`；重复会话 |

### 3.6 第 2 天验收

```bash
python manage.py makemigrations --check --dry-run     # 无遗留
python manage.py migrate
python manage.py seed_tags
python manage.py test tests.test_constraints
```

再对 8 张业务表执行 `psql ... -c "\d+ <table>"`，逐表对照 database.md，核对约束名、索引名、NOT NULL、默认值，结果记入 `backend/file/design_manuscript/week1_checklist.md`（由你建；一行一表，打勾即可）。

## 4 第 3 天：rules、policies、notify、audit

这一天结束后 B 就可以开始写招聘发布和申请投递（只读底层已齐）。

### 4.1 `recruitments/rules.py`（纯函数，不碰数据库，一律传入 `now`）

```python
def add_one_year(dt: datetime) -> datetime            # 2 月 29 日回退到 2 月 28 日
def validate_deadline(deadline: datetime, now: datetime) -> None
    # 要求 now < deadline <= add_one_year(now)，否则 ValidationFailed(details={"deadline": ...})
def validate_headcount(min_headcount: int | None, max_headcount: int) -> None
    # 1 <= max <= settings.MAX_HEADCOUNT_LIMIT；min 为 None 或 1 <= min <= max；否则 ValidationFailed
def seven_day_deadline(r) -> datetime | None          # closed_at + 7 天
def retention_starts_at(r) -> datetime | None         # closed_at/full_at/deleted_at 中最早的非空
def retention_expires_at(r) -> datetime | None        # 起算点 + 180 天
def is_retention_expired(r, now) -> bool
def is_apply_open(r, now) -> bool                     # 未删除、open、now < deadline
def is_processable(r, now) -> bool
    # 未删除；(open 且 now < deadline) 或 (closed 且 now < closed_at + 7 天)；full 为 False
def is_editable(r, now) -> bool                       # 未删除、open、now < deadline
def is_publisher_deletable(r, now) -> bool            # 同 is_editable
```

边界一律用严格小于：`now == deadline` 视为已截止；`now == closed_at + 7 天` 视为已过窗口。

### 4.2 `recruitments/policies.py`

```python
def can_edit(user, r, now) -> bool            # 发布者 and is_editable
def can_close(user, r, now) -> bool           # 发布者 and open and now < deadline（open 必然未满员）
def can_delete(user, r, now) -> bool          # 发布者: is_publisher_deletable；管理员: 未删除
def can_view_applications(user, r) -> bool    # 仅发布者；管理员无特权
def publish_state_for_viewer(user, r, now) -> PublishView
    # PublishView(can_apply: bool, apply_blocked_reason: str | None)
    # 顺序：本人发布 → "own"；已删除/非 open/已过截止 → "not_open"；否则 (True, None)
    # 供详情接口直接使用，"本人招聘无投递键并标注"由此字段体现
```

### 4.3 `applications/policies.py`

```python
@dataclass(frozen=True)
class ApplicationAccess:
    relation: Literal["applicant", "publisher", "none"]
    can_view: bool
    can_see_note: bool
    can_see_applicant_name: bool      # 仅发布者且 can_view
    can_download_resume: bool
    can_see_publisher_mark: bool      # 仅发布者

def resolve_application_access(user, app, recruitment, now) -> ApplicationAccess
def can_submit_application(user, recruitment, now, *, has_active_application: bool) -> None
def can_modify_application(user, app, recruitment) -> bool
def can_withdraw_application(user, app, recruitment) -> bool
def can_process_application(user, app, recruitment, now) -> bool
```

`resolve_application_access` 的判定表（必须全部写成测试）：

| 条件 | relation | can_view | can_see_note | can_download_resume | 其他 |
|------|----------|----------|--------------|---------------------|------|
| 既非申请人也非发布者（含管理员） | none | False | False | False | 全 False |
| 已过留存期限（`is_retention_expired`） | 原关系 | False | False | False | 全 False |
| 申请人，status ∈ {processing, accepted, rejected} | applicant | True | True | True | 不可见 `publisher_mark` |
| 申请人，status ∈ {withdrawn, invalid} | applicant | True | True | False | 能看到自己的状态与自己写的说明 |
| 发布者，status ∈ {processing, accepted, rejected} | publisher | True | True | True | `can_see_applicant_name`、`can_see_publisher_mark` 为 True |
| 发布者，status ∈ {withdrawn, invalid} | publisher | True | False | False | `can_see_applicant_name` 为 True，`can_see_publisher_mark` 为 False |
| 申请人与发布者是同一人 | 不可能（提交时已拒绝），出现则按 publisher 处理并记 ERROR 日志 | | | | |

`can_submit_application` 按此顺序检查并抛对应错误码：申请人是发布者 → `SELF_APPLICATION_FORBIDDEN`；`privacy_consented_at` 为空 → `PRIVACY_NOT_CONSENTED`；`not is_apply_open` → `RECRUITMENT_NOT_OPEN`；`has_active_application` → `DUPLICATE_APPLICATION`。`has_active_application` 由调用方（B）在持有招聘锁的事务内查询后传入，A 不在 policy 里查库。

`can_modify_application` / `can_withdraw_application`：操作者是申请人、`status == processing`、招聘 `deleted_at is None`。`can_process_application`：操作者是发布者、`status == processing`、`is_processable`。

### 4.4 `notifications`

`types.py`（常量，且所有申请事件类型以 `application_` 开头）：

| 常量 | 值 | 接收人 | application_id |
|------|-----|--------|----------------|
| APPLICATION_SUBMITTED | application_submitted | 发布者 | 必填 |
| APPLICATION_ACCEPTED | application_accepted | 申请人 | 必填 |
| APPLICATION_REJECTED | application_rejected | 申请人（含自动拒绝，`context["auto"]=True`） | 必填 |
| APPLICATION_WITHDRAWN | application_withdrawn | 发布者 | 必填 |
| APPLICATION_UPDATED | application_updated | 发布者 | 必填 |
| RECRUITMENT_CLOSED | recruitment_closed | 发布者（到期自动关闭时） | 空 |
| RECRUITMENT_UPDATED | recruitment_updated | 申请人 | 必填 |
| RECRUITMENT_DELETED | recruitment_deleted | 申请人、管理员删除时另含发布者 | 申请人必填，发布者空 |
| ADMIN_REMOVED | admin_removed | 发布者 | 空 |

`ALL`、`APPLICATION_EVENTS`（前缀为 `application_` 的子集）、`REQUIRES_APPLICATION`（上表"必填"的子集）三个集合从常量自动生成，测试保证三者一致。

`templates.py`：`render(type, context) -> (title, content)`。`context` 只允许键 `recruitment_title`、`status_label`、`link`、`auto`、`reason_label`；出现其他键直接抛 `ValueError`（防止有人把简历内容或申请人信息塞进去）。内容里不出现申请人姓名。每种类型一条模板，固定中文文案，标题 ≤ 100 字。

`service.py::notify(...)`（签名见总规划 4.5）实现细节：
1. `assert_in_atomic()`。
2. 类型在 `REQUIRES_APPLICATION` 内而 `application is None` 或 `recruitment is None` → `ValueError`。
3. 类型属于 `APPLICATION_EVENTS` 且 `rules.is_retention_expired(recruitment, clock.now())` → 返回 `None`。
4. `render` → 创建 `Notification`。
5. `recipient.email_notify_enabled` 为真 → 创建 `EmailLog(to_email=recipient.email, status=pending, attempts=0)`，并 `transaction.on_commit(lambda: mail.dispatch(log_id))`。
6. 返回通知对象。

`mail.py`（本周）：`dispatch(email_log_id)` 只 `logger.info("email dispatch reserved", extra={...})` 后返回，不改状态；其余函数留空壳并抛 `NotImplementedError("reserved for week 2")`。

### 4.5 `audit`

`actions.py` 五个常量；`service.record(...)` 按总规划 4.8 实现：`actor` 非空时快照 `actor_role`、`actor_is_admin`，为空时三个字段同为 `None`；`reason` 超过 500 字截断；`target_type` 必填。

### 4.6 第 3 天测试

- `tests/recruitments/test_rules.py`：每个函数覆盖边界（`now == deadline`、`now == closed_at + 7 天`、`2024-02-29` 加一年、deleted、各状态）。
- `tests/applications/test_policies.py`：4.3 判定表每一行一条；`can_submit_application` 四种拒绝各一条。
- `tests/notifications/test_notify.py`：类型前缀一致性、缺 `application` 报错、过期返回 None、邮件开关两种、`on_commit` 触发（在 `TxTestCase` 里用 `captureOnCommitCallbacks(execute=True)`）、context 非法键。
- `tests/audit/test_audit.py`：actor 为 None、reason 截断、模型不可改不可删。

### 4.7 第 3 天交付给 B/C 的东西（第一次放行）

可以 import 并依赖：`core.*`、全部 `models`、`rules`、两份 `policies`、`notify`、`audit.record`、`tests/base.py` 与 `factories.py`。此后这些签名不改；要改走总规划 3.3 的流程。

## 5 第 4 天：state + files

### 5.1 `recruitments/state.py`

**`sync_recruitment(recruitment_id, *, now=None) -> SyncResult`**

```
assert_not_in_atomic()
now = now or clock.now()
with transaction.atomic():
    r = lock_recruitment(recruitment_id)
    if r.deleted_at: return SyncResult(False, 0, False)
    closed = False; rejected = 0
    if r.status == "open" and now >= r.deadline:
        r.status = "closed"; r.closed_at = r.deadline; r.close_reason = "deadline"
        r.save(update_fields=["status","closed_at","close_reason","updated_at"])
        notify(publisher, RECRUITMENT_CLOSED, recruitment=r)
        closed = True
    if r.status == "closed" and now >= r.closed_at + 7天:
        rejected = reject_processing_applications(r, decided_at=r.closed_at + 7天, reason="closed_timeout")
return SyncResult(closed, rejected, False)
```

要点：只更新 `status='processing'` 的申请，所以重复调用不产生第二次拒绝与通知；`full` 状态不处理（满员时已经拒绝完）。

**`reject_processing_applications(r, decided_at, reason) -> int`**
1. `assert_in_atomic()`，并断言调用者持有该招聘的锁（通过 `lock_recruitment` 设置的标记，见 5.2）。
2. `ids = list(Application.objects.select_for_update().filter(recruitment=r, status="processing").values_list("id", flat=True))`（按 id 排序，保证加锁顺序稳定）。
3. 一条 `UPDATE`：`status="rejected"`、`decided_at=decided_at`、`publisher_mark="none"`、`has_unseen_update=False`、`updated_at=clock.now()`。
4. 为每个被拒绝的申请调用 `notify(applicant, APPLICATION_REJECTED, recruitment=r, application=app, context={"auto": True, "reason_label": ...})`。
5. 返回数量。`reason` 只用于选文案与日志，不入库。

**`mark_full(r, now)`**
1. `assert_in_atomic()`。
2. 若 `r.status == "open"` 且 `now >= r.deadline` 且 `closed_at is None`：补写 `closed_at = deadline`、`close_reason = "deadline"`（同一条 UPDATE，不覆盖 full）。若已有 `closed_at` 则保持原值。
3. 同一条 UPDATE 写 `status="full"`、`full_at = r.full_at or now`。
4. `reject_processing_applications(r, decided_at=r.full_at, reason="full")`。

调用 `mark_full` 之前，调用方必须已把 `accepted_count` 加到等于 `max_headcount`（否则 `recruitment_full_chk` 不拦、但语义不对）；A 在函数内断言 `r.accepted_count >= r.max_headcount`，不满足抛 `ValueError`。

**`run_in_recruitment_tx(recruitment_id, fn)`** 按总规划 3.2 实现。要点：
- 事务一 `sync_recruitment(recruitment_id, now=now)` 在 `atomic` 之外调用。
- 事务二内 `lock_recruitment`，把"当前持有锁的招聘 id"记在 `tx.py` 的线程本地变量里，供 `lock_application` 和 `reject_processing_applications` 校验，离开事务二时清除。
- `fn(r, now)` 抛任何异常，只回滚事务二。
- 招聘不存在 → 在事务一之前抛 `NotFound`。

### 5.2 `core/tx.py` 补充

`_held = threading.local()`；`lock_recruitment` 在 `atomic` 内成功后 `_held.recruitment_id = id`；提供 `held_recruitment_id()` 与上下文清理，用于 `lock_application`、`reject_processing_applications`、`mark_full` 的断言，避免 B 忘记先锁招聘。

### 5.3 `files/storage.py` 与 `files/validators.py`

按总规划 4.6 的签名实现，补充以下具体规则：

- 扩展名：取原文件名最后一个 `.` 之后的小写部分，必须在 `{"pdf","doc","docx"}`，否则 `reason="type"`。
- 大小：`upload.size` 与实际读取字节数两处都校验，> 10485760 → `reason="size"`；空文件 → `reason="size"`。
- 文件头：
  - pdf：前 5 字节为 `%PDF-`。
  - doc：前 8 字节为 `D0 CF 11 E0 A1 B1 1A E1`。
  - docx：前 4 字节为 `PK\x03\x04`，且 `zipfile` 能打开并含 `[Content_Types].xml` 与至少一个以 `word/` 开头的条目。
  - 不满足 → `reason="signature"`。扩展名与文件头类型必须一致。
- 展示名清洗：取最后一个路径分隔符（`/` 与 `\`）之后的部分，去掉控制字符，空则用 `resume.<ext>`，截断到 255 字节且保留扩展名。
- 存储路径：`resumes/YYYY/MM/<uuid4hex>.<ext>`，以 `os.open(..., O_CREAT|O_EXCL)` 写入；写完 `fsync`。路径始终由代码拼出，不含任何用户输入。
- `open_resume(path)`：先 `os.path.realpath` 并确认位于 `PRIVATE_FILE_ROOT/resumes` 内，否则抛 `PermissionError`。
- `discard_resume`：同样做路径检查；文件不存在返回 True；其他失败写 WARNING 日志返回 False。
- `staged_resume`：`save_resume` 后 `yield`；`except BaseException` 里 `discard_resume` 再 `raise`。
- `cleanup_orphans`：本周只写函数与单元测试，不挂命令。

### 5.4 第 4 天测试

- `tests/recruitments/test_state.py`（全部 `TxTestCase`，用 `clock.freeze`）：
  1. 截止前后：`now = deadline - 1s` 不动；`now = deadline` 变 closed，`closed_at == deadline`，发布者收到一条通知。
  2. 七天边界：`closed_at + 7天 - 1s` 不拒绝；`== closed_at + 7天` 全部拒绝，`decided_at == closed_at + 7天`，每个申请人恰好一条通知。
  3. 幂等：连续调用 `sync_recruitment` 三次，通知与拒绝数不变。
  4. 任务延迟：`now = deadline + 30 天` 一次调用，直接得到 closed 且全部拒绝，`decided_at` 仍是业务时间。
  5. `mark_full`：open 未过期、open 且已过期但 `closed_at` 为空（构造）、closed 手动关闭三种；断言 `closed_at/close_reason` 的保留或补写，以及 `status='full'`、`full_at`。
  6. `run_in_recruitment_tx`：fn 抛业务异常后，事务一产生的关闭仍在库里；嵌在外层 `atomic` 里调用抛 `RuntimeError`。
  7. 并发：两个线程同时对同一招聘的同一申请执行"锁招聘 → 复核 → 接受 → `accepted_count+1`"，只有一个成功（用 `threading.Barrier`；这是对 `lock_recruitment` 行锁的验证）。
- `tests/files/test_storage.py`：三种合法文件通过；伪装扩展名（txt 改名 pdf）、超 10MB、空文件、扩展名与文件头不符、docx 缺 `word/` 各一条拒绝；文件名含 `../` 与 `\`；`staged_resume` 异常后文件被清理；`open_resume` 路径穿越被拒。

### 5.5 第 4 天交付给 B（第二次放行）

`state.*`、`files.*` 可用。B 此时能完整写发布、投递、接受、拒绝、暂留的 service。

## 6 第 5 天：accounts + 契约测试

### 6.1 accounts

- `identity.py`：`resolve_role(real_id)` 用 0 表第 10 条的临时规则并写 `TODO`；`is_tongji_email(email)` 校验域名在 `ALLOWED_EMAIL_DOMAINS`。
- `sso.py`：定义 `SSOIdentity` 数据类与 `SSOProvider` 抽象类、`DevSSOProvider`；`CasSSOProvider` 的方法抛 `NotImplementedError("reserved")`。
- `services.py`：
  - `login_with_sso(identity) -> User`：按 `sso_subject` 找，找不到按 `real_id` 找并绑定 subject，仍无则创建（`role=resolve_role`、`nickname=name`、`is_admin=False`）；必填信息缺失抛 `BizError(AUTH_FAILED)`；`is_active=False` 抛 `Forbidden`。
  - `update_profile`：昵称 1–32 字，去首尾空白；邮件开关布尔。
  - `give_privacy_consent`：首次写 `privacy_consented_at`，已有则不覆盖。
- `backends.py`、`AUTHENTICATION_BACKENDS` 注册。
- 视图与路由（A 自己写，全部走统一信封）：

| 接口 | 要点 |
|------|------|
| `GET /auth/csrf` | `@ensure_csrf_cookie`，返回 `{csrf_token}`，公开 |
| `POST /auth/dev-login` | 仅当 `DEBUG and ALLOW_DEV_LOGIN`，否则路由不注册；body `{real_id, name?, email?}`；响应同 `/me` |
| `POST /auth/logout` | 清会话 |
| `GET /me` | `uid, nickname, name, role, is_admin, email, email_notify_enabled, privacy_consented` |
| `PATCH /me` | 昵称、邮件开关 |
| `POST /me/privacy-consent` | 幂等 |
| `GET /auth/sso/login`、`/auth/sso/callback` | 本周返回 501，`code=INTERNAL_ERROR`，message 写"预留" |

`/me` 返回 `name`（本人真实姓名）和 `email`，其他用户的接口不返回这两项（发布者看申请人姓名走 `can_see_applicant_name`，由 B 的序列化器决定）。

### 6.2 契约测试（最重要的一条）

`tests/contract/test_week1_flow.py`：**只通过 A 的接口和 ORM** 把"发布 → 投递 → 接受 → 满员"完整跑一遍，等于给 B 一份可执行的参考实现。它自己写少量胶水函数（`_publish`、`_apply`、`_accept`，放在测试文件内，不进 `apps/`），按下面的顺序调用：

```
_publish: validate_deadline + validate_headcount → 创建 Recruitment + RecruitmentTag（标签必须 is_active）
_apply:   staged_resume → run_in_recruitment_tx(fn):
              can_submit_application(has_active_application=查库) → 创建 Application
              → notify(发布者, APPLICATION_SUBMITTED)
_accept:  run_in_recruitment_tx(fn):
              lock_application → 复核 can_process_application → 状态 accepted、decided_at=now
              → accepted_count+1 → notify(申请人, APPLICATION_ACCEPTED)
              → 若 accepted_count == max_headcount: mark_full
```

断言场景：
1. 名额 1：A、B 都投递，接受 A → A=accepted，招聘 full，B 被自动拒绝，A、B 各一条通知，发布者两条（两次投递）+ 一条关闭相关通知为零。
2. 名额 2：接受一个后仍 open；再接受第二个转 full。
3. 本人投递被拒；未同意隐私被拒；重复投递被拒；撤回（直接改库为 withdrawn）后重投成功并生成新记录。
4. 截止时间已过未同步：直接调用 `_apply`，事务一先把招聘置 closed，投递被拒 `RECRUITMENT_NOT_OPEN`，且 closed 状态已提交。
5. 关闭后七天内接受成功；第 7 天整点接受被拒 `PROCESSING_WINDOW_CLOSED`，且剩余申请已被自动拒绝。
6. 接受后 `accepted_count` 与 accepted 状态申请数一致。
7. 管理员既非申请人也非发布者：`resolve_application_access` 全 False。

**这份测试全绿，才代表 A 的底层可以放给 B 全面使用。**

### 6.3 第 5 天验收

```bash
python manage.py check && python manage.py makemigrations --check --dry-run
python manage.py test tests
```

## 7 第 6 天：预留位、文档、补洞

### 7.1 预留位（都只放文件，不实现）

| 位置 | 内容 |
|------|------|
| `notifications/mail.py` | `send_email_log`、`retry_pending_emails` 抛 `NotImplementedError("reserved for week 2")` |
| `recruitments/retention.py` | `purge_expired_applications` 抛同样错误 |
| `accounts/sso.py::CasSSOProvider` | 同上 |
| `files/jobs.py` | `cleanup_orphans` 的命令包装预留 |
| 管理命令 | `run_sync_recruitments`、`run_purge_applications`、`run_send_emails`、`run_cleanup_orphan_files`、`run_cleanup_audit_logs`：每个命令类 `handle` 抛 `CommandError("reserved")`；`run_sync_recruitments` **本周要做真实现**（见下） |
| `chat`、`feed` | 只有 models / 空 app |

`run_sync_recruitments` 真实现（20 行）：查出两类候选（`open` 且 `deadline <= now`；`closed` 且 `closed_at + 7 天 <= now` 且存在 processing 申请），逐个 `sync_recruitment`，每个单独 `try/except` 并记日志，最后打印处理数量。因为 B 的集成测试和你的演示都需要它。

### 7.2 给 B、C 的交接文档

在 `backend/README_for_app_devs.md`（由你建，一页纸）写：
1. 可 import 的清单（本文 4.7、5.5 的并集）和 "禁止改动" 目录。
2. 写操作固定模板（`run_in_recruitment_tx` + 契约测试里的 `_apply`/`_accept`）。
3. 错误码表（直接引用 `ErrorCode`）。
4. 响应信封和分页用法。
5. 本地启动：`migrate`、`seed_tags`、`dev-login` 的 curl 示例。
6. 提需求改底层的流程。

### 7.3 补洞

- `python manage.py check --deploy --settings=config.settings.prod`（使用假环境变量），记录警告并逐条处理或在清单里注明原因。
- 跑一遍全量测试 3 次，确认并发测试不偶发失败；偶发就改成显式同步而不是加 `sleep`。
- 扫描：`grep -rn "timezone.now" apps/`（只应出现在 `core/clock.py`）；`grep -rn "print(" apps/`（应为空）。

## 8 第 7 天：缓冲

只处理：前六天没收口的测试、B/C 提出的底层缺口、database.md 三处同步（由你决定）、`week1_checklist.md` 打勾。不再新增功能。

## 9 每天的完成标准（卡点）

| 天 | 必须通过 | 放行给谁 |
|----|----------|----------|
| 1 | `check`、`tests.core`、`/healthz` | — |
| 2 | `migrate` 成功、约束测试全绿、8 表核对完成、`seed_tags` 可重复执行 | — |
| 3 | rules/policies/notify/audit 测试全绿 | B 可开始发布与投递 |
| 4 | state/files 测试全绿，含并发 | B 可开始接受/拒绝/暂留 |
| 5 | 契约测试全绿，accounts 接口可用 | B、C 可联调 |
| 6 | 全量测试连跑 3 次无偶发失败，交接文档完成 | — |

## 10 我没有验证、需要你实现时留意的地方

- DRF 与 Django 6.1 的兼容性、`pg_trgm` 权限、`CheckConstraint(condition=...)` 的参数名（Django 5.1 起把 `check` 改为 `condition`，6.1 沿用）在你的环境里都没有实际跑过。第一次 `check`/`migrate` 报错时以报错为准。
- `UniqueConstraint(Lower("email"))`、`GinIndex(opclasses=...)`、`db_default=Now()` 在 Django 6.1 的写法我是按 5.x 之后的稳定用法写的，同样没有运行验证。
- 并发测试里"两个线程抢同一行锁"依赖真实 PostgreSQL，不能用 SQLite。
- 本文的临时身份规则（`t` 开头为教师）只是开发期占位，不代表同济的真实编号规则。
