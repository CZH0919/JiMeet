# Sprint2 后端开发规划：公告、登录权限与招聘申请流程验收

版本：v1.0｜日期：2026-11-12｜状态：待实施  
代码基线：`016aa3b`。文件路径均相对项目根目录；HTTP 路径统一以 `/api/v1` 为前缀，不带末尾斜杠。  
分工：**zf 负责阶段 1～3，czh 负责阶段 4～6；阶段 3 验收后交接。** 阶段编号表示依赖与验收顺序，不对应固定天数。

## 1. 目标与范围

### 1.1 目标

在现有 Django/DRF、PostgreSQL 后端上完成本阶段四项工作：补齐竞赛与活动公告接口；补齐同济邮箱登录与管理员身份入口；核对并修正招聘/申请流程中的 200 人上限、撤回、暂留、处理、截止/满员、删除失效及通知；完成从公告发布到申请处理的联调验收。交付物是前端可直接对接的接口、可复现的 HTTP 调用序列、测试证据和交付记录。

**本阶段只做上述范围，不按《软件需求规格说明 2.0 修订稿》全量实现。** 现有招聘、申请、通知、私有文件代码除 200 人上限配置和验收中确认的阻塞性缺陷外，不重构、不改写业务规则、不改历史迁移、不删除已有字段。

### 1.2 本阶段验收口径

| 用户给出的阶段 | 后端交付 | 通过标准 |
| --- | --- | --- |
| 1. 竞赛与活动公告栏目（FR-09、3.2） | 公告查询、详情、发布、编辑、删除接口；公告审计；按发布时间的稳定排序；报名截止/活动时间及报名链接字段 | 管理员可发布、编辑、删除；普通用户可浏览列表和详情；列表按发布时间倒序；详情返回 `time_kind`、`event_at`、`link_url` 及正文；删除为软删除且详情返回 404 |
| 2. 公告管理所需的登录与权限（FR-01、FR-02、FR-09） | 同济邮箱验证码登录；管理员身份判定与授予命令；公告接口权限校验 | 非 `@tongji.edu.cn` 邮箱被拒；验证码可完成登录并建立会话；`/me` 返回 `is_admin`；非管理员发布/管理公告返回 403；现有 `dev-login` 不受影响 |
| 3. 补齐已有招聘和申请流程（FR-05～FR-08） | 200 人上限配置修正；对撤回、暂留、接受/拒绝、截止、满员、删除失效、PDF 上传、站内通知和个人申请状态逐项核对，修复阻塞缺陷 | 200 人上限生效；撤回后可重投；暂留不产生终态；接受不超员且满员自动拒绝其余处理中申请；截止后停止投递并保留七天处理窗口；删除后处理中/已接受申请变 `invalid`；对应通知可达；`GET /me/applications` 可查看本人申请状态 |
| 4. 联调和验收 | 端到端 HTTP 序列、权限拒绝、满员/删除边界、回归与交付文档 | 主流程可复现；越权、重复操作、最后名额竞争、截止边界、删除失效均有明确结果；全量测试通过并记录已知限制 |

### 1.3 范围边界

| 纳入本阶段 | 本阶段不展开 |
| --- | --- |
| 公告模型现有数据层之上的 HTTP 接口、序列化、路由、权限、测试和文档 | 公告置顶排序、公告站内通知、公告邮件、公告举报/审核工作流 |
| 同济邮箱验证码登录（请求验证码、校验并建立会话）；保留现有 `dev-login` | 学校统一身份认证（CAS/SSO）真实接入；独立注册、密码登录 |
| 管理员身份判定复用现有 `is_admin`；补充受控的管理员授予/撤销命令 | 在线授予/撤销管理员、管理员角色体系、管理员操作后台页面 |
| 200 人上限修正及招聘/申请全流程核对、缺陷修复、通知验证 | 聊天、个性化推荐、完整管理后台、前端页面实现、生产部署、留存物理清理、周期任务平台 |
| 后端接口契约、HTTP 验收脚本/示例、测试记录和交付索引 | 真实邮件服务上线、真实简历数据、生产 SMTP 凭据 |

### 1.4 关键决策

| 事项 | 本阶段决策 | 理由与影响 |
| --- | --- | --- |
| 同济邮箱登录 | 现有 `dev-login` 只做开发身份，不是 FR-01 的邮件验证登录。本阶段新增“邮箱验证码登录”，与 `dev-login` 并存，不替换、不修改现有开发登录。 | `dev-login` 校验邮箱域名但不发送/验证邮件，不能作为 FR-01 验收依据。新接口为增量能力，旧联调方式继续可用。 |
| 邮箱验证码形式 | 6 位数字验证码，有效期 10 分钟，同一邮箱 60 秒内不可重复请求，最多尝试 5 次，成功后一次性消费；数据库只存 HMAC 摘要，不存明文。 | 满足“发送认证邮件、验证后建立会话、失败明确提示”；避免明文凭证落库。 |
| 邮件发送 | 开发/测试使用控制台或内存邮件后端；生产默认关闭邮箱登录，显式开启时必须配置 SMTP，缺失配置时端点返回 503，不静默降级为控制台。 | 本阶段不部署真实邮件服务，但保留生产接入路径；验收不依赖真实收件箱。 |
| 管理员身份 | 继续使用 `User.is_admin` 和 `core.permissions.IsAdminFlag`，不新增角色表；新增 `set_admin` 管理命令用于受控授予/撤销，Django Admin 现有入口保留。 | 现有权限模型已可用；命令解决联调时“如何得到管理员测试身份”的可复现问题。 |
| 200 人上限 | 将 `settings.MAX_HEADCOUNT_LIMIT` 由 50 调整为 200，并同步测试、文档和模型说明；不新增数据库迁移。 | 现库 CHECK 只约束 `max_headcount >= 1`，上限是应用层常量；修改是需求口径修正，不改变已有数据。 |
| 公告排序 | 公告列表严格按 `created_at DESC, id DESC`。现有 `is_pinned` 字段和 `list_announcements()` 的置顶优先行为保留给内部/历史使用，但**不进入 Sprint2 HTTP 契约**。 | 阶段标准明确要求“按发布时间倒序”；若把 `is_pinned` 暴露给写接口，会出现置顶公告排在最前而违反验收口径。公开查询新增 `list_public_announcements()`，不改已有数据层函数和测试。 |
| 公告删除权限 | 发布者本人或任一 `is_admin` 用户可删除；编辑仅发布者本人，其他管理员不能编辑。 | 与 FR-09 及 `backend/design_file/design_manuscript/announcement_plan.md` 已确认决定一致。 |
| 公告通知 | 发布、编辑、删除公告不生成站内通知，也不新增 `Notification` 关联字段。 | 本阶段需求只到 FR-09；公告通知属于 FR-08/FR-11 的扩展，需改通知模型和迁移，不纳入本阶段。 |
| 前端页面 | 本仓库只有后端。首页默认展示公告、切到招聘页、个人主页展示申请状态均由前端按契约实现；后端交付以接口契约和 HTTP 序列验收，前端就绪后再做浏览器联调。 | 避免把“页面完成”当成后端交付前提；与 Sprint1 的交付口径保持一致。 |

本次不以 SRS 3.3 的量化性能指标作为硬性验收门槛，重点保证业务正确、权限明确、状态/人数一致、事务可回滚和接口可复现。

## 2. 实现基础与工作基线

### 2.1 当前代码状态

| 模块 | 现状 | 本阶段动作 |
| --- | --- | --- |
| 接口总量 | `backend/design_file/api.md` 记录 31 个可用方法/路径、2 个 SSO 501 预留；公告 5 个路径标注“待实现（数据层已完成）”。 | 新增 7 个路径（2 个邮箱登录、5 个公告），可用方法/路径增至 38；公告状态改为可用。 |
| 公告 `apps/announcements/` | 已有 `Announcement` 模型、迁移、`selectors.py`、`services.py`、`admin.py` 和数据层测试；**没有** `serializers.py`、`views.py`、`urls.py`，`config/urls.py` 未挂载。 | 补齐 HTTP 层、路由、序列化、权限与 API 测试。 |
| 账号 `apps/accounts/` | 已有 `User.is_admin`、`IsAdminFlag`、Session/CSRF、`/auth/dev-login`、`/me`、隐私确认；`DevSSOProvider` 只做开发身份；没有邮件验证码、邮件发送配置、管理员授予命令。 | 新增邮箱验证码登录、管理员授予命令、邮件配置与测试；不改 `dev-login` 行为。 |
| 招聘 `apps/recruitments/` | 发布、列表、详情、修改、关闭、删除、我的招募已实现；`MAX_HEADCOUNT_LIMIT = 50`；状态补执行与满员逻辑已实现。 | 改为 200；核对截止、满员、删除失效和并发边界；只修阻塞缺陷。 |
| 申请 `apps/applications/` | 提交、修改、撤回、重投、接受、拒绝、暂留/取消暂留、已阅确认、我的申请、发布者申请列表已实现；PDF/DOC/DOCX 上传与私有存储已实现。 | 逐项联调；核对 200 上限、撤回后可重投、暂留、满员自动拒绝、删除失效、通知和个人申请状态。 |
| 私有文件 `apps/files/` | 简历扩展名/大小/文件头校验、私有存储、鉴权下载、发布者查看审计已实现。 | 复核 PDF 上传、10 MiB 边界、撤回/失效后禁读、跨用户权限拒绝；不改存储模型。 |
| 通知 `apps/notifications/` | 9 种通知类型、列表/未读数/单条已读/全部已读已实现；申请/招聘事件已接入；`Notification` 没有公告外键。 | 核对申请接受/拒绝/撤回/修改、招聘修改/关闭/删除、管理员删除的通知接收人和去重；公告通知不纳入。 |
| 审计 `apps/audit/` | 已有 `announcement_publish/update/delete` 动作常量；公告服务在同一事务内写审计。 | 公告 HTTP 层复用现有服务，确保删除理由写入 `reason`。 |
| 测试 | `backend/tests/` 已有账号、招募、申请、通知、文件、公告数据层测试；Sprint1 至 Sprint2 记录为 204 项通过。 | 以本轮实际运行结果重新记录；新增邮箱登录、公告 API、200 上限、端到端和通知专项测试。 |

**主要参考：** `file/tasks/软件需求规格说明2.0修订稿.md` 的 FR-01、FR-02、FR-05～FR-09、3.2；`backend/design_file/api.md`（唯一接口正文）；`backend/design_file/design_manuscript/announcement_plan.md`（公告已确认决定）；`backend/design_file/design_manuscript/database.md` 1.9（公告表）；`Project_Progress_Record/Sprint1_BackEnd/` 与 `Sprint1_to_2_BackEnd/` 的阶段记录。

### 2.2 可复用组件

| 组件 | 位置 | 用途 |
| --- | --- | --- |
| `PrivateAPIView`、`validate_data` | `backend/apps/core/views.py` | 认证、CSRF、严格查询参数、私有缓存头、输入校验。 |
| `ok`、`created`、`page`、`envelope` | `backend/apps/core/responses.py` | 统一响应信封与分页。 |
| `paginate` | `backend/apps/core/pagination.py` | 默认每页 20、最大 50；越界页返回空列表。 |
| `StrictSerializer`、`StrictCharField`、`StrictIntegerField`、`AwareDateTimeField`、`QueryIntegerField` | `backend/apps/core/serializers.py` | 拒绝未知/重复字段，拒绝布尔/字符串冒充整数，要求显式时区。 |
| `IsAuthenticatedBiz`、`IsAdminFlag` | `backend/apps/core/permissions.py` | 登录校验与 `is_admin` 校验。 |
| `BizError`、`Forbidden`、`NotFound`、`ValidationFailed`、`Conflict` | `backend/apps/core/errors.py` | 统一错误码与 HTTP 状态。 |
| `clock.now()`、`clock.freeze()` | `backend/apps/core/clock.py` | 业务时间与时间边界测试。 |
| `run_in_recruitment_tx`、`sync_recruitment`、`mark_full` | `backend/apps/recruitments/state.py` | 状态补执行、招募锁、满员处理。 |
| `notify` | `backend/apps/notifications/service.py` | 事务内生成站内通知和邮件待发送记录。 |
| `record` | `backend/apps/audit/service.py` | 业务审计。 |
| `staged_resume`、`save_resume`、`open_resume` | `backend/apps/files/storage.py` | 暂存、校验、私有读取和失败清理。 |
| `TxTestCase`、`make_user`、`make_recruitment`、`make_application` | `backend/tests/base.py`、`backend/tests/factories.py` | 真实提交、行锁、测试数据构造。 |

### 2.3 差距清单

| 编号 | 差距 | 影响 | 处理阶段 |
| --- | --- | --- | --- |
| G1 | 公告只有数据层，没有 HTTP 接口和路由；`config/urls.py` 未挂载公告 | 前端无法发布/浏览公告 | 阶段 3 |
| G2 | 没有同济邮箱验证码登录；`dev-login` 不发送/验证邮件 | FR-01 无法验收 | 阶段 2 |
| G3 | `MAX_HEADCOUNT_LIMIT = 50`，与需求 200 不一致 | 招聘人数上限不满足需求 | 阶段 4 |
| G4 | 管理员只能通过 Django Admin 手工配置，缺少可脚本化的授予方式 | 联调管理员身份不易复现 | 阶段 2 |
| G5 | 招聘/申请主流程已实现，但缺少按本阶段验收口径整理的端到端证据 | 无法证明撤回、暂留、满员、删除失效、通知一致 | 阶段 4～6 |
| G6 | 公告没有通知外键，公告删除不会通知发布者 | 本阶段不要求；若按 FR-08/FR-11 验收则需扩展 | 明确不纳入 |
| G7 | 仓库无前端代码 | 首页默认公告、切招聘页、个人主页无法由本仓库完成浏览器验收 | 以 HTTP 契约验收；前端另行联调 |

### 2.4 基线检查

阶段 1 先执行并记录以下命令；任何失败必须查明原因，不能直接记为后续阶段通过：

```bash
cd backend
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
python manage.py test tests --keepdb --noinput --settings=config.settings.test
git rev-parse HEAD
git status --short
```

同时核对：PostgreSQL 可连接；`backend/var/private` 或测试私有目录可写；`seed_tags` 可执行；`/healthz`、`/auth/csrf`、`/me` 可访问；现有 `dev-login` 仅在 `DEBUG` 与 `ALLOW_DEV_LOGIN` 同时开启时可用。

## 3. 分阶段安排

| 阶段 | 负责人 | 主题 | 交付与通过条件 |
| --- | --- | --- | --- |
| 1 | zf | 基线与接口约定 | 环境、迁移、测试基线；Sprint2 契约草案；差距与决策记录。 |
| 2 | zf | 同济邮箱登录与管理员身份 | 验证码登录可用；管理员授予命令可用；`dev-login` 回归通过。 |
| 3 | zf | 公告查询与管理接口 | 5 个公告路径可用；权限、排序、校验、审计测试通过；提交中期交接。 |
| 4 | czh | 招聘与申请流程补齐 | 200 上限生效；撤回/暂留/接受拒绝/截止/满员/删除失效/PDF 上传核对通过。 |
| 5 | czh | 通知联动与个人申请状态 | 事件通知接收人正确、无重复；`GET /me/applications` 状态可查。 |
| 6 | czh（zf 复核） | 联调、回归与交付 | 端到端、权限拒绝、满员/删除边界通过；全量回归和交付文档完成。 |

### 3.1 阶段 1：基线与接口约定（zf）

**工作内容**

- 按 2.4 执行环境、迁移和全量测试基线；记录实际通过、失败、跳过数量，不直接沿用历史数字。
- 核对 `backend/design_file/api.md` 为唯一接口正文；在文档中新增 Sprint2 契约草案（邮箱登录、公告、200 上限、错误码），暂标“待实现”。
- 确认本计划 1.4 的关键决策；如团队对邮箱登录范围、公告置顶或公告通知另有决定，先记录变更再实施。
- 确认公告现有模型字段足够支撑 FR-09：`title`、`content`、`time_kind`、`event_at`、`link_url`、`recruitment`、`author`、`deleted_at`；不新增公告字段。
- 确认 200 上限修改点：`settings.MAX_HEADCOUNT_LIMIT`、`apps/recruitments/models.py` 说明、`tests/test_base.py` 断言、`api.md` 5.2 与 400 示例；无数据库迁移。

**交付与通过条件**

- 形成 `Project_Progress_Record/Sprint2_BackEnd/Record/stage_01_baseline.md`，记录命令、结果、环境版本、差距和决策。
- `api.md` Sprint2 契约草案字段、错误码、权限和状态口径完整，前端可据此评审。
- 现有测试基线明确；失败项有处置结论；工作分支和提交基线记录清楚。

### 3.2 阶段 2：同济邮箱登录与管理员身份（zf）

**工作内容**

- 新增 `EmailLoginCode` 模型与迁移：`email`、`code_digest`、`expires_at`、`attempts`、`consumed_at`、`created_at`；只存 HMAC 摘要，不存明文验证码。
- 新增 `apps/accounts/email_login.py`：签发验证码、校验有效期/尝试次数/一次性消费、发送邮件、限流；新增 `login_with_verified_email`，按邮箱查找或首次创建用户。
- 新增两个公开接口：`POST /auth/email/code`、`POST /auth/email/login`；均强制 CSRF，成功登录轮换 CSRF 并返回与 `/me` 相同的资料。两个路由始终注册，视图内按 `ALLOW_EMAIL_LOGIN` 决定是否返回 404，避免运行期开关变化导致 URL 不重建。
- 新增 `set_admin` 管理命令：按 `real_id` 或 `email` 授予/撤销 `is_admin`，幂等，不提供 HTTP 入口。
- 配置：`ALLOW_EMAIL_LOGIN`、验证码 TTL、重发间隔、最大尝试次数、`EMAIL_BACKEND`、`DEFAULT_FROM_EMAIL`、`EMAIL_HOST`、`EMAIL_PORT`、`EMAIL_HOST_USER`、`EMAIL_HOST_PASSWORD`、`EMAIL_USE_TLS`；dev/test 默认控制台/内存后端，prod 默认关闭邮箱登录，显式开启但未配置 SMTP 时端点返回 503，不静默使用控制台。
- 更新 `api.md` 第 4 章和错误码；新增 `tests/accounts/test_email_login.py`、`test_admin_command.py`；更新 `tests/test_schema.py` 的模型清单。

**关键规则**

- 邮箱必须符合 `ALLOWED_EMAIL_DOMAINS`（默认 `tongji.edu.cn`）；域名不符返回 400，不发送邮件。
- 验证码 6 位数字、10 分钟有效、同一邮箱 60 秒内不可重复请求、最多 5 次尝试、成功或过期后不可复用；错误/过期统一返回 401 `AUTH_FAILED`，不泄露邮箱是否存在。
- 首次登录按邮箱创建本地用户：`is_admin=False`、`privacy_consented_at=None`；`real_id` 由邮箱本地部分派生（1～32 位；超长或冲突时用稳定哈希），`name` 取本地部分（截断至 32 字），`role` 沿用现有展示用前缀规则，`sso_subject` 写入 `email:` 前缀的稳定哈希；不授予任何额外权限。
- 已有同邮箱账号直接登录，不修改姓名、昵称、角色或管理员标记；停用账号返回 403。
- `dev-login` 保持原行为；现有测试、CSRF、Session 逻辑不得回归。

**交付与通过条件**

- 真实 HTTP 可完成“取 CSRF → 请求验证码 → 从控制台/测试邮件读取验证码 → 登录 → `/me` 返回 `is_admin`”。
- 域名拒绝、错误验证码、过期、重复使用、重发限流、停用账号、CSRF 缺失均有测试。
- `set_admin` 可将普通用户变为管理员并撤销；撤销后发布新公告返回 403。
- `python manage.py test tests.accounts tests.test_schema` 通过；全量回归无新增失败。
- 形成 `Record/stage_02_auth.md`。

### 3.3 阶段 3：公告查询与管理接口（zf）

**工作内容**

- 新增 `apps/announcements/serializers.py`：列表项、详情、创建/更新输入、分页查询；复用 `PublicUserSerializer` 输出 `uid/nickname/role`。
- 新增 `apps/announcements/views.py`、`urls.py`，并在 `backend/config/urls.py` 挂载：
  - `GET /announcements`：已登录，分页，仅未删除，严格按 `created_at DESC, id DESC`。
  - `GET /announcements/{id}`：已登录，未删除，返回详情与当前用户权限。
  - `POST /announcements`：`is_admin`，201。
  - `PATCH /announcements/{id}`：仅发布者本人，部分更新。
  - `DELETE /announcements/{id}`：发布者本人或任一 `is_admin`，软删除，`reason` 可选。
- 新增 `selectors.list_public_announcements()`，严格按发布时间倒序；保留现有 `list_announcements()` 和公告数据层测试不变。
- 复用 `create_announcement`、`update_announcement`、`soft_delete_announcement`；权限在视图层判断，写服务继续负责事务与审计。
- 更新 `api.md` 第 8 章，把 5 个公告路径改为可用，并写明本阶段不暴露 `is_pinned`。
- 新增 `tests/announcements/test_api.py`：CRUD、权限、排序、分页、字段校验、审计、删除后 404。

**字段与校验**

- `title`：去首尾空白后 1～100 字；`content`：去首尾空白后 1～2000 字纯文本；`time_kind`：`deadline`/`event`。
- `event_at`：带时区 ISO 8601；创建时必须严格晚于当前时间；PATCH 仅在提交 `event_at` 或 `time_kind` 时校验生效时间，避免历史公告无法改正文。
- `link_url`：可空，最多 500 字，仅允许 `http`/`https` 绝对地址；空串/null 归一为 null。
- `recruitment_id`：可空正整数；提交时目标招募必须存在且未删除；关联招募后续被删除时公告保留，详情返回 `recruitment_available=false`。
- 不接受 `is_pinned`、`author`、`created_at`、`updated_at`、`deleted_at` 等字段；未知字段返回 400；PATCH 至少提供一个可写字段，空对象返回 400。

**交付与通过条件**

- 管理员可发布、编辑自己的公告、删除任意公告；普通用户只能浏览；非作者管理员可删除但不能编辑。
- 列表严格按发布时间倒序；删除后列表不返回、详情 404；审计动作和删除理由正确。
- 非法字段、无时区时间、过去时间、非法链接、已删除招募关联均返回 400；未登录 401，越权 403。
- 5 个公告路径均可通过 HTTP 调用；`tests.announcements` 与全量回归通过。
- 更新 `api.md`，提交 `Record/stage_03_handoff.md`，明确阶段 4～6 尚未验证的招聘/申请项；czh 按材料复现后再接手。

**中期交接边界：** zf 交付“邮箱登录 + 管理员授予 + 公告完整 HTTP 接口 + 契约与测试证据”；czh 从阶段 4 起负责招聘/申请流程核对、通知联动、端到端验收和最终交付。czh 不修改 zf 已交付接口的字段与错误码；确需变更时先记录影响并通知 zf。

### 3.4 阶段 4：招聘与申请流程补齐（czh）

**工作内容**

- 将 `settings.MAX_HEADCOUNT_LIMIT` 改为 200；同步 `apps/recruitments/models.py` 说明、`tests/test_base.py` 断言、`api.md` 5.2 和 400 示例；确认无迁移。
- 新增 200 边界测试：创建 200 成功、201/0/布尔/浮点/数字字符串拒绝；`min_headcount > max_headcount` 拒绝；修改上限不得低于 `accepted_count`；接受第 200 人进入 `full` 并自动拒绝其余处理中申请。
- 逐项核对 FR-05～FR-08：
  - 撤回：仅申请人、仅 `processing`、招聘未删除；撤回后发布者不能看简历；可重新投递并生成新记录，旧记录保留。
  - 暂留/取消暂留：仅发布者、仅处理窗口内、仅 `processing`；状态仍为 `processing`，不通知申请人；重复操作幂等。
  - 接受/拒绝：接受增加 `accepted_count`，达到上限转 `full`；拒绝为终态；重复操作 409；最后名额竞争最多一份成功。
  - 截止/满员：`now >= deadline` 停止新投递并投影为 `closed`；未满员的关闭招聘保留七天处理窗口；满员优先于关闭；到达七天边界自动拒绝；重复补执行不重复通知。
  - 删除失效：发布者仅在进行中且未删除时可删；管理员可删任意未删除招聘；`processing/accepted` 转 `invalid`，`rejected/withdrawn` 不变；删除后禁止新申请、编辑、处理；重复删除 404。
- 核对 PDF 上传：`multipart/form-data` 单文件、`%PDF-` 文件头、非空、10 MiB 边界、缺失/伪造/超限 400；私有路径不出现在响应；撤回/失效后下载 403；无关用户/管理员 404；发布者下载写审计。
- 只修验收中确认的阻塞缺陷；不改已有状态枚举、事务锁顺序、响应字段和权限模型。若发现需要改共享模型或契约，先记录并与 zf 对齐。

**交付与通过条件**

- 200 上限在 API、服务规则和测试中一致；任何路径都不会使 `accepted_count > max_headcount`。
- 撤回、重投、暂留、接受、拒绝、截止、七天、满员、删除失效的专项测试通过；并发最后名额测试不超员。
- PDF 上传/下载/禁读边界通过；原有 DOC/DOCX 能力不回退。
- 全量回归无新增失败；形成 `Record/stage_04_flow.md`。

### 3.5 阶段 5：通知联动与个人申请状态（czh）

**工作内容**

- 按 FR-08 核对通知矩阵，不新增公告通知：
  - 申请提交 → 发布者；撤回 → 发布者；修改 → 发布者；接受/拒绝 → 申请人；满员自动拒绝/关闭超时自动拒绝 → 申请人（含原因）；招聘修改 → 变更前 `processing/accepted` 申请人；招聘删除 → 本次转 `invalid` 的申请人；管理员删除 → 申请人失效通知 + 发布者 `admin_removed`。
- 核对通知只在业务成功后生成、同一事件不重复、只返回本人可见通知、已读/全部已读/未读数范围一致；通知不包含简历内容或多余个人信息。
- 核对 `GET /me/applications`：返回本人全部申请（含撤回），`status`、`decided_at`、招募引用 `is_deleted` 正确；七天边界投影为 `rejected`；支持 `status`、`recruitment_id` 筛选；越权/不存在筛选结果为空。
- 只修阻塞缺陷；若现有通知类型/模板已满足，不新增类型、不改 `Notification` 模型。
- 新增 `tests/notifications/test_sprint2_events.py` 和必要的 `tests/applications/test_me_applications.py`。

**交付与通过条件**

- 每个事件的通知接收人、关联 `recruitment_id/application_id`、未读数和去重符合契约。
- 申请人能从 `GET /me/applications` 看到处理中/已接受/已拒绝/已撤回/已失效及 `decided_at`；发布者能从申请列表看到暂留和未读修改标记。
- 撤回/失效后简历和说明的可见性收紧；通知入口不绕过对象权限。
- 形成 `Record/stage_05_notifications.md`。

### 3.6 阶段 6：联调、回归与交付（czh，zf 复核）

**工作内容**

- 按第 7 节执行端到端 HTTP 序列：管理员发布公告 → 普通用户查看公告 → 切到招聘列表 → 提交申请 → 发布者处理 → 申请者收到通知并查看状态；再覆盖权限拒绝、满员、截止、删除失效和 CSRF。
- 新增 `tests/contract/test_sprint2_flow.py`，用真实 Session/CSRF 串联公告、招聘、申请、通知；必要时补一个可复制的 HTTP/PowerShell 示例。
- 运行全量回归、`check`、`makemigrations --check --dry-run`、`git diff --check`；记录通过、失败、跳过及原因。
- 更新 `api.md` 最终状态；形成 `Record/stage_06_acceptance.md` 和 `Record/sprint2_delivery.md`。
- zf 复核阶段 2～3 的邮箱登录和公告实现，修复验收中发现的公告/登录缺陷；czh 负责招聘/申请/通知侧缺陷闭环。

**交付与通过条件**

- 主流程和边界矩阵全部通过；越权返回 403/404 符合契约；满员/删除/截止边界无超员、无重复通知、无部分写入。
- 全量测试通过（Windows 符号链接场景如无权限可跳过并记录）；无新增迁移差异；接口文档与实际行为一致。
- 交付记录包含版本、提交号、运行命令、测试结果、示例调用和已知限制；其他同学可按记录独立复现。

## 4. 接口交付清单

### 4.1 本阶段新增接口

| 阶段 | 方法 | 路径 | 权限 | 成功 | 说明 |
| --- | --- | --- | --- | --- | --- |
| 2 | POST | `/auth/email/code` | 公开，强制 CSRF | 200，`data.expires_in`、`data.resend_after` | 校验邮箱域名并发送 6 位验证码；不泄露邮箱是否已注册。 |
| 2 | POST | `/auth/email/login` | 公开，强制 CSRF | 200，本人资料 | 校验验证码，建立 Session 并轮换 CSRF；首次登录创建本地用户。 |
| 3 | GET | `/announcements` | 已登录 | 200，分页公告 | 仅未删除；严格按 `created_at DESC, id DESC`；列表项含正文和链接。 |
| 3 | GET | `/announcements/{id}` | 已登录 | 200，公告详情 | 不存在/已删除 404；含正文、时间、链接、关联招募和当前用户权限。 |
| 3 | POST | `/announcements` | `is_admin` | 201，公告详情 | 发布公告；作者为当前用户；写 `announcement_publish` 审计。 |
| 3 | PATCH | `/announcements/{id}` | 仅发布者本人 | 200，公告详情 | 部分更新；其他管理员不能编辑；写 `announcement_update` 审计。 |
| 3 | DELETE | `/announcements/{id}` | 发布者或任一 `is_admin` | 200，`data=null` | 软删除；`reason` 可选 1～500 字；写 `announcement_delete` 审计。 |

新增 7 个方法/路径后，可用方法/路径由 31 增至 38；`/auth/sso/login`、`/auth/sso/callback` 仍为 501 预留。

### 4.2 本阶段复用的现有接口

| 用途 | 方法/路径 |
| --- | --- |
| 会话与身份 | `GET /auth/csrf`；`POST /auth/dev-login`（仅开发环境，保留）；`POST /auth/logout`；`GET /me`；`PATCH /me`；`POST /me/privacy-consent` |
| 招聘 | `GET /tags`；`GET/POST /recruitments`；`GET/PATCH/DELETE /recruitments/{id}`；`POST /recruitments/{id}/close`；`GET /me/recruitments` |
| 申请 | `POST/GET /recruitments/{id}/applications`；`GET /me/applications`；`GET /applications/{id}`；`GET /applications/{id}/resume`；`PATCH /applications/{id}`；`POST /applications/{id}/withdraw`、`accept`、`reject`、`hold`、`unhold`、`read` |
| 通知 | `GET /notifications`；`GET /notifications/unread-count`；`POST /notifications/{id}/read`；`POST /notifications/read-all` |
| 健康检查 | `GET /healthz`（仅环境检查，不要求登录） |

### 4.3 公告接口契约

**公告列表项**：`id`、`title`、`content`、`time_kind`、`event_at`、`link_url`、`recruitment_id`、`publisher`、`created_at`、`updated_at`。列表返回正文，首页如需摘要由前端截断，不新增字段。

**公告详情**：列表项全部字段，加 `recruitment_available`、`permissions`。

**与 `api.md` 第 8 章草案的差异：** 不暴露 `is_pinned`；详情新增 `recruitment_available` 和 `permissions`；其余字段沿用草案。

| 字段 | 类型/约束 | 列表 | 详情 | 写入 |
| --- | --- | --- | --- | --- |
| `id` | 正整数 | 是 | 是 | 只读 |
| `title` | 1～100 字，去首尾空白 | 是 | 是 | 必填 |
| `content` | 1～2000 字纯文本 | 是 | 是 | 必填 |
| `time_kind` | `deadline`（报名截止）/`event`（活动时间） | 是 | 是 | 必填 |
| `event_at` | 带时区 ISO 8601；创建时须晚于当前时间 | 是 | 是 | 必填 |
| `link_url` | 可空，≤500 字，仅 `http/https` 绝对地址 | 是 | 是 | 可选，可清空 |
| `recruitment_id` | 可空正整数；目标须存在且未删除 | 是 | 是 | 可选，可清空 |
| `recruitment_available` | 布尔；关联招募存在且未删除时为 true | 否 | 是 | 只读/计算 |
| `publisher` | `{uid, nickname, role}`，不含姓名/邮箱/主键 | 是 | 是 | 只读 |
| `permissions` | `{can_edit, can_delete}` | 否 | 是 | 只读/计算 |
| `created_at` / `updated_at` | 带时区 ISO 8601 | 是 | 是 | 只读 |

详情示例（发布者本人查看）：

```json
{
  "id": 12,
  "title": "2026 年 ACM 校赛报名",
  "content": "报名方式：登录校赛系统提交队伍信息，并在截止前完成确认。",
  "time_kind": "deadline",
  "event_at": "2026-11-30T23:59:59+08:00",
  "link_url": "https://example.tongji.edu.cn/acm",
  "recruitment_id": 101,
  "recruitment_available": true,
  "publisher": {
    "uid": "0123456789abcdef0123456789abcdef",
    "nickname": "赛事管理员",
    "role": "teacher"
  },
  "created_at": "2026-11-12T10:00:00+08:00",
  "updated_at": "2026-11-12T10:00:00+08:00",
  "permissions": {"can_edit": true, "can_delete": true}
}
```

**权限与错误**

- 未登录：401 `UNAUTHENTICATED`。
- 非管理员发布：403 `FORBIDDEN`；非作者编辑：403；非作者且非管理员删除：403。
- 公告不存在或已删除：404 `NOT_FOUND`；重复删除同样 404。
- 字段/查询参数不合法：400 `VALIDATION_ERROR`；未知/重复查询键 400；错误媒体类型 415；方法不支持 405。
- 列表分页默认 1/20，最大 50；越界页返回空列表；`total` 为未删除公告总数。
- 发布/编辑/删除在业务事务内写审计；删除理由写入 `AuditLog.reason`；不生成站内通知。
- 不暴露 `is_pinned`；不提供置顶/取消置顶接口。

### 4.4 邮箱登录契约

| 接口 | 请求 | 成功 | 失败 |
| --- | --- | --- | --- |
| `POST /auth/email/code` | JSON `{"email":"s123@tongji.edu.cn"}`；先 `GET /auth/csrf`，带 `X-CSRFToken` | 200，`data={"expires_in":600,"resend_after":60}` | 400 域名/格式非法；429 `RATE_LIMITED`；503 `EMAIL_UNAVAILABLE`；403 CSRF 失败 |
| `POST /auth/email/login` | JSON `{"email":"s123@tongji.edu.cn","code":"123456"}`；先 `GET /auth/csrf`，带 `X-CSRFToken` | 200，与 `GET /me` 相同的资料；建立 Session 并轮换 CSRF | 401 `AUTH_FAILED`（错误/过期/已用/尝试过多）；403 `FORBIDDEN`（停用）；400 字段非法；403 CSRF 失败 |

**验证码规则**

- 6 位数字，TTL 600 秒，重发间隔 60 秒，最多 5 次尝试；同一邮箱新验证码签发后旧验证码失效；成功/过期/超次后不可复用。
- 邮箱去首尾空白并按小写规范化后存储和查询，大小写不同视为同一邮箱；验证码签发、校验和用户查找使用同一规范化结果。
- 数据库仅保存 `HMAC-SHA256(SECRET_KEY, email + ":" + code)`；日志、响应和审计不得包含明文验证码。
- 邮件只包含验证码、有效期和“非本人操作请忽略”，不包含简历、申请或招聘业务信息。
- 首次登录创建用户：`is_admin=False`、隐私未确认、无可用密码；`real_id` 由邮箱本地部分派生（1～32 位；超长或冲突时使用 `em` + SHA-256 前 30 位），`name` 取本地部分（截断至 32 字），`role` 沿用现有展示用前缀规则，`sso_subject` 写入 `email:` 前缀的稳定哈希；不授予管理员权限。
- 已有同邮箱账号直接登录，不修改资料；停用账号 403；不通过该入口提交 `is_admin`、`role`、`real_id` 等字段。
- `role` 仅用于主页标注与通知称谓，沿用现有开发前缀规则（`t`/`T` 开头为教师），不作为权限依据；正式师生身份仍待学校 SSO 接入后替换。
- `dev-login` 保留，生产仍由 `ALLOW_DEV_LOGIN` 禁止；邮箱登录由 `ALLOW_EMAIL_LOGIN` 控制，prod 默认关闭，启用时必须配置 SMTP。

### 4.5 错误码补充

| code | HTTP | 使用场景 |
| --- | --- | --- |
| `RATE_LIMITED` | 429 | 同一邮箱在重发间隔内重复请求验证码；响应 `data.details.retry_after` 为剩余秒数。 |
| `EMAIL_UNAVAILABLE` | 503 | 显式启用邮箱登录但生产 SMTP 未配置，或验证码邮件发送失败；提示稍后重试，不生成可登录的验证码。 |
| `AUTH_FAILED` | 401 | 验证码错误、过期、已使用或尝试次数超限；不区分具体原因。 |
| `VALIDATION_ERROR` | 400 | 邮箱格式/域名、公告字段、分页参数或查询参数不合法。 |
| `FORBIDDEN` | 403 | 非管理员发布公告、非作者编辑、非作者且非管理员删除、停用账号、CSRF 失败。 |
| `NOT_FOUND` | 404 | 公告不存在/已删除；邮箱登录开关关闭时也按 404 处理。 |

现有错误码（`UNAUTHENTICATED`、`RECRUITMENT_NOT_OPEN`、`DUPLICATE_APPLICATION`、`APPLICATION_NOT_PROCESSING`、`RECRUITMENT_FULL`、`PROCESSING_WINDOW_CLOSED`、`HEADCOUNT_BELOW_ACCEPTED`、`INVALID_RESUME_FILE` 等）保持不变。

### 4.6 前端对接要点

- 顺序：`GET /auth/csrf` → `POST /auth/email/code` → 用户输入验证码 → `POST /auth/email/login` → 再次 `GET /auth/csrf` → 业务写请求。`sessionid` 为 HttpOnly Cookie，前端不读取。
- 首页默认调用 `GET /announcements`；切到招聘页调用现有 `GET /recruitments`；两者使用同一 Session，不需要新接口。
- 公告列表项按 `created_at` 倒序展示；`time_kind` 决定文案为“报名截止”或“活动时间”；`link_url` 有值时展示报名/相关链接；正文随列表/详情返回，详情页展示完整正文。
- 公告详情用 `permissions.can_edit`/`can_delete` 控制按钮；列表未返回 `permissions` 时，前端可用 `publisher.uid` 与 `/me.uid` 比较并结合 `is_admin` 推导，详情以 `permissions` 为准。发布入口用 `/me` 的 `is_admin` 控制，不与普通用户入口混用。
- 招聘/申请/通知继续使用现有契约；删除确认可使用发布者详情中的 `application_counts` 展示受影响数量。
- 文件上传使用 `multipart/form-data`，浏览器生成 boundary；PDF 成功下载返回文件流，不是 JSON 信封。

## 5. 实现规范与框架巩固

### 5.1 文件落点

| 阶段 | 新增/修改 | 内容 |
| --- | --- | --- |
| 2 | `backend/apps/accounts/models.py`、`migrations/0002_*.py` | `EmailLoginCode`；只存摘要；索引 `(email, -created_at)`。 |
| 2 | `backend/apps/accounts/email_login.py`、`services.py`、`serializers.py`、`views.py`、`urls.py` | 验证码签发/校验/发送；邮箱身份登录；请求校验；两个公开视图与路由。 |
| 2 | `backend/apps/accounts/management/commands/set_admin.py` | 按 `real_id`/`email` 授予或撤销 `is_admin`；幂等。 |
| 2 | `backend/config/settings/base.py`、`dev.py`、`test.py`、`prod.py`、`.env.example` | 邮件后端、SMTP、TTL/重发/尝试次数、`ALLOW_EMAIL_LOGIN`。 |
| 2 | `backend/tests/accounts/`、`backend/tests/test_schema.py`、`api.md` | 邮箱登录、管理员命令、模型清单、契约。 |
| 3 | `backend/apps/announcements/selectors.py` | 新增 `list_public_announcements()`；保留原函数。 |
| 3 | `backend/apps/announcements/serializers.py`、`views.py`、`urls.py` | 公告列表/详情/写入/查询；5 个视图；路由。 |
| 3 | `backend/config/urls.py`、`backend/tests/announcements/test_api.py`、`api.md` | 挂载、API 测试、契约状态。 |
| 4 | `backend/config/settings/base.py`、`apps/recruitments/models.py`、`tests/test_base.py`、`api.md` | 50→200 及说明/断言/文档。 |
| 4～5 | `backend/tests/recruitments/`、`tests/applications/`、`tests/notifications/`、`tests/contract/` | 200 边界、撤回/暂留/处理、截止/满员/删除、通知、端到端。 |
| 6 | `Project_Progress_Record/Sprint2_BackEnd/Record/` | 阶段记录、交接、交付索引。 |

### 5.2 分层与复用

1. 视图只做认证、权限、输入校验和响应组装；业务规则放在 service/policy/state，查询放在 selector，权限判断复用 `core.permissions` 和对象关系。
2. 公告写操作复用既有 `services.py`，不在视图重复写审计或事务；邮箱登录的验证码签发/校验独立成模块，用户查找/创建复用 `UserManager` 和现有账号服务。
3. 新接口统一使用 `PrivateAPIView`（登录后）或显式 CSRF 的公开 `APIView`；响应使用 `ok/created/page`，错误使用 `BizError` 子类。
4. 序列化器拒绝未知字段、重复字段和隐式类型转换；时间字段使用 `AwareDateTimeField`；分页继续使用 `core.pagination.paginate`。
5. 不新增运行时依赖；邮件使用 Django 自带 `send_mail`，不引入第三方邮件 SDK。

### 5.3 事务、并发与一致性

- 公告创建/更新/删除沿用现有服务的事务与审计；HTTP 层不外包大事务。
- 招聘/申请继续使用“先补执行、再招募锁、再申请锁”的顺序；本阶段不改锁顺序，只在验收中发现缺陷时按现有 `core.tx`/`state.py` 修复。
- 接受最后名额、满员自动拒绝、撤回与接受竞争必须由行锁和事务保证；禁止先读后写或依赖前端状态。
- 删除招聘时 `processing/accepted → invalid`、通知、审计在同一事务提交；重复删除不重复产生失效事件。
- 邮箱验证码消费与用户创建使用短事务；会话建立放在验证成功后；发送邮件失败不得留下可登录的验证码。

### 5.4 校验、安全与隐私

- 邮箱域名使用现有 `is_tongji_email` 和 `ALLOWED_EMAIL_DOMAINS`；不信任客户端 MIME、文件名或 `is_admin` 字段。
- 验证码只存摘要、常数时间比较、限流、限次、一次性消费；日志不记录验证码、完整邮箱或认证凭证。应用层做邮箱级限流；生产可在反向代理/网关增加 IP 级限流，避免把来源 IP 写入业务库。
- 公告 `content` 按纯文本处理，不解释 HTML；`link_url` 只允许 `http/https`，防止 `javascript:`/`data:` 等伪协议。
- 公告发布者只返回 `uid/nickname/role`；不返回 `real_id`、邮箱、数据库主键或内部路径。
- 简历继续私有存储，下载前复核申请人/发布者关系、申请状态和留存期；管理员无额外读取权限。
- 生产配置缺失关键邮件变量时，显式启用邮箱登录的部署应启动失败或端点 503；未启用时端点 404，不静默降级。

### 5.5 数据模型与迁移

- 公告不新增字段、不改迁移；`is_pinned` 保留但本阶段不暴露。
- 新增 `EmailLoginCode` 一张表及迁移；字段、索引、`db_table` 明确，迁移由 `makemigrations` 生成，不手写冲突迁移。
- 200 上限不涉及迁移；现有 `recruitment_max_headcount_chk` 只要求 `>= 1`。
- 迁移检查必须为 `No changes detected`；不重写历史迁移、不重建已有数据库。

### 5.6 测试

| 测试层 | 覆盖 |
| --- | --- |
| 单元/服务 | 验证码签发/校验/限流/过期/一次性；200 上限规则；撤回/暂留/接受/拒绝/满员/删除失效；通知生成与去重。 |
| API | 公告 5 个路径的成功/失败/权限/分页/排序/审计；邮箱登录两个路径的 CSRF、字段、错误码；现有招聘/申请/通知接口回归。 |
| 合同/端到端 | 真实 Session/CSRF 串联公告→招聘→申请→处理→通知→个人状态；权限拒绝、满员、截止、删除。 |
| 回归 | `python manage.py test tests --keepdb --noinput --settings=config.settings.test`；`check`；`makemigrations --check --dry-run`；`git diff --check`。 |

测试数据使用虚构邮箱、虚构姓名和最小 PDF；不提交真实简历、真实邮箱或 SMTP 凭据。Windows 无符号链接权限时，沿用现有跳过项并记录原因。

### 5.7 文档

- `backend/design_file/api.md` 仍是唯一接口正文；`api_before.md` 不重复维护新接口。
- 公告章节删除“待实现”状态，写明本阶段不暴露 `is_pinned`、不发公告通知。
- 邮箱登录章节写明验证码规则、错误码、开发/生产邮件配置和 `dev-login` 的关系。
- 招聘章节把人数上限示例从 50 改为 200。
- 阶段记录放 `Project_Progress_Record/Sprint2_BackEnd/Record/`，不把过程性说明塞进 `api.md`。

## 6. 中期交接要求

阶段 3 结束前，zf 完成以下材料；czh 先按材料复现，再继续阶段 4。

| 内容 | 最低要求 |
| --- | --- |
| 代码基线 | 仓库、分支、完整提交号；迁移/配置变化；以经过评审的提交为接手基线，保留已有作者和历史。 |
| 已交付能力 | 按接口列出邮箱登录、管理员命令、公告 5 个路径的可用方法、关键行为、错误码和验证结果；标明阶段 4～6 尚未验证的招聘/申请项。 |
| 运行复现 | Python/PostgreSQL 版本、依赖安装、环境变量、迁移、`seed_tags`、启动命令；邮箱验证码在开发环境从哪里读取（控制台/内存邮件）；管理员如何授予。 |
| 调用契约 | `backend/design_file/api.md` 为唯一正文；公告和邮箱登录章节状态与实际一致；列出与阶段 1 草案的差异。 |
| 验证证据 | 公告 CRUD/权限/排序/审计、邮箱登录成功/失败/限流/CSRF、`dev-login` 回归；说明未运行项和原因。 |
| czh 后续任务 | 对应阶段 4～6 列出依赖、修改位置、复用服务和通过条件；涉及契约变更时记录影响并通知 zf。 |

**交接纪律：** zf 未提交、未通过自测或未写清复现步骤的能力，不视为已交付；czh 不基于未提交的本地改动继续开发。阶段 3 的公告/登录缺陷由 zf 在阶段 6 前闭环，招聘/申请/通知缺陷由 czh 闭环。

## 7. 联调与验收

### 7.1 主流程

1. `GET /auth/csrf` 获取令牌与 Cookie。
2. 管理员邮箱 `POST /auth/email/code`，从开发控制台/测试邮件读取 6 位验证码；`POST /auth/email/login` 建立会话，`GET /me` 确认 `is_admin=true`。若使用开发身份，可 `POST /auth/dev-login` 后用 `set_admin` 授予。
3. 管理员 `POST /announcements` 发布公告（`time_kind=deadline`，`event_at` 为未来时间，`link_url` 可选）；`GET /announcements` 确认公告出现在列表首位；`GET /announcements/{id}` 确认正文、时间、链接。
4. 管理员 `PATCH /announcements/{id}` 修改标题/正文，`GET` 确认更新；另建一条公告确认两条按发布时间倒序。
5. 普通用户邮箱登录（`is_admin=false`）；`GET /announcements` 200；`POST/PATCH/DELETE /announcements` 均 403；`GET /recruitments` 200，确认可从公告页切到招聘页。
6. 普通用户 `POST /me/privacy-consent`；`GET /tags`；`GET /recruitments/{id}` 找到可投递招募；`POST /recruitments/{id}/applications` 上传最小 PDF，`GET /me/applications` 看到 `processing`。
7. 发布者 `GET /recruitments/{id}/applications` 看到申请；`POST /applications/{id}/hold`（可再 `unhold`）；`POST /applications/{id}/accept`；申请人 `GET /notifications` 收到接受通知，`GET /me/applications` 状态为 `accepted`。
8. 删除公告：作者或另一管理员 `DELETE /announcements/{id}`，再次 `GET` 为 404，列表不再返回；审计记录存在且理由正确。
9. 删除招聘：发布者/管理员 `DELETE /recruitments/{id}`，申请人 `GET /me/applications` 状态为 `invalid`，收到失效通知，简历下载 403。

### 7.2 边界与权限矩阵

| 场景 | 操作 | 预期 |
| --- | --- | --- |
| 公告权限 | 非作者普通用户 POST/PATCH/DELETE；非作者管理员 PATCH；非作者管理员 DELETE | 403；403；200（管理员可删） |
| 公告校验 | 缺标题/正文、正文超 2000、无时区/过去 `event_at`、非法 `link_url`、已删除 `recruitment_id`、提交 `is_pinned` | 400 `VALIDATION_ERROR`，不写库 |
| 公告排序 | 连续发布两条公告 | 列表按 `created_at DESC, id DESC`，新公告在前 |
| 公告删除 | 作者删除、另一管理员删除、重复删除 | 200、200、404；软删除；审计理由正确 |
| 邮箱登录 | 非同济域名、错误验证码、过期、重复使用、60 秒内重发、停用账号、缺 CSRF | 400、401、401、401、429、403、403 |
| 200 上限 | 创建值 `200`、`201`、`0`、布尔/浮点/字符串；修改到低于 `accepted_count` | `200` 成功；其余 400/409；数据库不超限 |
| 满员 | 接受第 200 人；再接受其他处理中申请 | 招聘转 `full`；其余自动 `rejected` 并通知；再接受 409 `RECRUITMENT_FULL` |
| 截止 | `now >= deadline` 后投递；关闭后 7 天内接受；到达 7 天边界 | 投递 409；7 天内可处理；边界后申请投影 `rejected`，处理 409 |
| 撤回/重投 | 申请人撤回后重新投递；发布者查看撤回记录 | 撤回 200；重投生成新 ID；旧记录保留；撤回后简历不可下载 |
| 暂留 | 发布者 hold/unhold；申请人查看状态 | 申请人仍见 `processing`；发布者见 `publisher_mark=hold`；不产生通知 |
| 删除失效 | 删除含 `processing/accepted/rejected/withdrawn` 的招聘；重复删除 | `processing/accepted → invalid`，其余不变；重复删除 404；不重复通知 |
| 通知权限 | 用户读取/标记他人通知；管理员读取他人申请 | 404；404 |
| PDF | 合法 PDF、缺失文件、伪造 PDF、10 MiB、10 MiB+1 | 201、400、400、201、400；响应不含私有路径 |
| 简历禁读 | 撤回/失效后申请人或发布者下载；无关用户/管理员下载 | 403；404 |

### 7.3 验证命令与证据

```bash
cd backend
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
python manage.py test tests --keepdb --noinput --settings=config.settings.test
git diff --check
```

记录实际输出：通过/失败/跳过数量、失败原因、修复提交、复测结果。HTTP 验收保留请求方法、路径、状态码、关键响应字段和请求 ID；不记录验证码、密码、真实简历或完整邮箱。

### 7.4 前端/浏览器说明

本仓库无前端代码，阶段 6 以真实 HTTP + Session/CSRF 序列作为后端验收。若前端页面已就绪，再补浏览器验收：首页默认展示公告、切到招聘页、公告详情、个人主页申请状态、通知中心、删除二次确认。前端页面未完成不作为后端交付阻塞项，但接口字段、排序、权限和错误码必须与 `api.md` 一致。

## 8. 完成标准与版本管理

- 本阶段 7 个新增接口可用，31 个现有可用接口回归通过；公告 5 个路径从“待实现”改为“可用”。
- FR-01/FR-02/FR-09 可验收：邮箱验证码登录可用；`is_admin` 判定与授予可用；普通用户只读公告，管理员可发布/管理，作者可编辑，作者或管理员可删除。
- FR-05～FR-08 可验收：200 人上限、撤回重投、暂留、接受/拒绝、截止、满员、删除失效、PDF 上传、通知和个人申请状态均有实测证据。
- 权限拒绝、CSRF、字段校验、截止/七天、满员并发、删除幂等均有测试；失败路径不产生部分写入、不重复通知、不超员。
- `api.md` 与实际行为一致；阶段记录和交付索引齐全；无未说明的失败或跳过项。
- 现有招聘/申请/通知/文件能力不因本阶段修改而回退；除 200 上限配置外，不改变既有业务规则。
- 采用短期任务分支和小步提交：zf 使用 `feat/sprint2-backend-auth-announcements`，czh 使用 `feat/sprint2-backend-flow-acceptance`；阶段 3 交接后合并/评审，再进入阶段 4。提交前核对暂存范围，保留团队已有修改；不重写历史提交。
- 本地与服务器同步时记录提交号与文件清单；Git 推送不会自动同步 PR/MR 或评审评论，交付记录单独维护。

## 9. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 邮箱登录范围超出预期 | 阶段 2 工期增加，影响公告交接 | 阶段 1 先确认决策；按“验证码 + 现有 Session/CSRF”最小实现，不引入 SSO、密码、注册页面；邮件发送失败按 503 处理。 |
| 生产 SMTP 不可用或未配置 | 生产环境无法登录 | 本阶段验收使用控制台/内存后端；交付说明列出 SMTP 变量；prod 显式启用但未配置时端点 503，未启用时 404，不静默降级。 |
| 200 上限改动影响现有前端/测试 | 前端校验或旧示例不一致 | 同步修改 `api.md`、模型说明和测试；通知前端；旧数据 `max_headcount<=50` 不受影响。 |
| 公告置顶与“按发布时间倒序”冲突 | 验收排序不通过 | 本阶段不暴露 `is_pinned`，公开列表严格按发布时间；保留旧数据层函数，后续需要置顶时单独评审。 |
| 公告通知缺失 | 若按 FR-08/FR-11 验收会被认为不完整 | 本阶段明确只做 FR-09；公告通知需要新增通知关联字段/迁移，列入后续增量，不在本次偷偷扩表。 |
| 无前端代码 | 无法完成浏览器首页/切换页验收 | 以 HTTP 契约和真实 Session/CSRF 序列验收；前端就绪后补浏览器联调，不作为后端阻塞项。 |
| 管理员授予命令被误用 | 普通用户获得治理权限 | 命令仅限有服务器/数据库权限的运维执行；不暴露 HTTP；Django Admin 仍受 `is_staff` 控制；测试覆盖授予/撤销。 |
| 历史测试数字与当前不一致 | 交付记录失真 | 阶段 1 重新跑基线，以本轮实际结果为准；失败/跳过逐项记录原因，不沿用旧数字。 |
