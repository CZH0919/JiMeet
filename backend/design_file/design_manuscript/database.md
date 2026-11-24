# JiMeet 后端数据库设计

本文说明当前模型、数据库约束与业务事务边界。接口字段和错误码以 `backend/design_file/api.md` 为准；开发与验收记录见 `Project_Progress_Record/`，历史变更通过 Git 追溯。

## 0 通用约定

1. 数据库：PostgreSQL；ORM：Django。表字段中的类型以 PostgreSQL 为准，括号内为 Django 对应写法。
2. 时间字段一律使用 `TIMESTAMPTZ`（`DateTimeField`，`USE_TZ = True`），不使用无时区的 DATETIME。
3. 枚举类字段（role、type、status 等）使用 `VARCHAR` + `CHECK` 约束（Django 中用 `TextChoices` + `CheckConstraint`），不使用 PostgreSQL 的 ENUM 类型，后续新增取值时迁移更简单。例外：`Notification.type`（1.5）和 `AuditLog.action`（1.8）取值会随功能频繁新增，有意不加 CHECK，由应用层常量约束。
4. 外键默认 `ON DELETE PROTECT`，业务删除采用软删除或状态变更；申请与简历长期保留，不按固定期限隐藏或物理清理。旧聚合字段仅为兼容保留，不据此恢复已丢失明细。
5. 招聘的修改、关闭、删除，以及申请的提交、修改、撤回、处理和自动处理，统一在事务中先用 `select_for_update()` 锁住对应的 Recruitment 行，再重新读取申请并校验当前状态、权限、删除标记和时间窗口；不得使用加锁前读取的状态作决定。需要锁申请行时，一律先锁招聘、再锁申请，防止并发重复接受、接受与撤回冲突及超员。状态变更、人数更新、站内通知与审计在同一事务内保存；当前不创建业务邮件任务或发信回调。
6. 需要由定时任务驱动的逻辑（Celery beat，或 management command + cron）：
   - 到截止时间，招聘自动置为已关闭；
   - 招聘关闭满 7 天，仍处理中的申请自动拒绝并通知；
   - 满员招聘若仍有处理中申请，补执行拒绝；
   - 邮件发送与重试保留为预留能力，当前不调度；
   - 孤立文件清理保留为预留能力；正常上传失败与替换由文件服务处理，不清理有效历史简历。
7. 定时任务不作为权限和时间校验的唯一保障。相关接口使用当前时间判断是否到期；必要时先补执行到期关闭或七天到期自动拒绝，再判断请求。补执行的状态、通知必须提交，即使原请求已不符合操作条件，也不能因业务拒绝而将补执行回滚。实现方式固定为两个独立事务：
   - 事务一：`sync_recruitment(recruitment_id)`，锁招聘行，按当前时间补执行到期关闭、七天自动拒绝、满员拒绝，状态历史与通知一并提交，不创建邮件任务；
   - 事务二：业务操作，重新锁招聘行，取得当前时间并重新读取申请；等锁期间跨越截止或七天边界时，先释放锁并独立补执行，再复核业务条件。事务二里的业务拒绝只回滚事务二。
   - 不使用 savepoint 包住补执行：这要求每一层都正确捕获业务异常，外层多包一层 atomic 就会让补执行整体回滚。
   定时任务只调用 `sync_recruitment`，与接口共用同一套状态流转。仅实际发生状态变更时生成通知，重复执行不得重复计数或通知。每次持锁后的业务操作使用同一时间快照，不复用加锁前已经过时的时间。
   自动处理使用业务时间而非任务实际运行时间：到期关闭取 `closed_at = deadline`；七天到期自动拒绝的 `decided_at` 取 `closed_at + 7 天`；满员触发的自动拒绝取 `full_at`。任务延迟不改变这些时间，通知的 `created_at` 仍是真实创建时间。
8. 事务实现约束：Django 设置 `ATOMIC_REQUESTS = False`（默认值），由 service 层显式开启事务；service 入口不得嵌在调用方的外层 `atomic` 中，否则第 7 条的“先提交补执行”无法成立。涉及加锁、并发和补执行的测试使用 `TransactionTestCase`，不用被外层事务包住的 `TestCase`。文件替换成功后的旧文件清理由 `transaction.on_commit` 执行；当前不挂接邮件派发回调。

## 1 实体及其字段定义

### 1.1 User 用户

Django 实现：继承 `AbstractBaseUser` + `PermissionsMixin`，`USERNAME_FIELD = "real_id"` 保留为内部标识；HTTP 账号认证使用邮箱与密码，`db_table = "app_user"`（`user` 是 PostgreSQL 保留字，避免每次都要加引号）。管理员权限只使用 `is_admin`，不与 Django 自带的 `is_staff` / `is_superuser` 混用（后两者仅用于 Django Admin 后台，由开发者持有）。

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY, 自增 | 数据库内的自增标识，不会对外公开 |
| uid | VARCHAR(32) | NOT NULL, UNIQUE | 对外随机标识（`uuid4().hex`，32 位）；资源权限仍须独立校验|
| real_id | VARCHAR(32) | NOT NULL, UNIQUE | 内部唯一兼容标识；邮箱注册时由服务端生成，不作为已验证的学号/工号，也不对外公开|
| nickname | VARCHAR(32)  | NOT NULL | 可以自主定义的用户名 |
| name | VARCHAR(32)  | NOT NULL | 用户自填姓名，仅作未核验展示 |
| email | VARCHAR(254) | NOT NULL（必须是同济邮箱格式） | 邮箱号，用于邮箱密码登录；后缀校验不代表归属已核验 |
| role | VARCHAR(32)  | NOT NULL，CHECK (role IN ('student','teacher')) | 展示身份 student 或 teacher；注册时可自填，不作授权依据；开发登录使用编号映射 |
| is_admin | BOOLEAN | NOT NULL，默认 FALSE | 是否拥有管理员权限 |
| is_active | BOOLEAN | NOT NULL，默认 TRUE | 是否启用 |
| password | VARCHAR(128) | NOT NULL DEFAULT '' | Django 密码哈希；邮箱密码注册时设置，旧开发账号可为不可用密码 |
| sso_subject | VARCHAR(191) | UNIQUE，可空 | 统一身份认证返回的稳定用户标识；与密码登录可并存 |
| email_notify_enabled | BOOLEAN | NOT NULL，默认 TRUE | 邮件偏好兼容字段，当前不控制发信 |
| privacy_consented_at | TIMESTAMPTZ | 可空 | 确认个人信息处理告知的时间；为空时不允许提交申请（首次填写简历前须确认） |
| last_login | TIMESTAMPTZ | 可空 | Django 内置字段，由 `AbstractBaseUser` 提供 |
| created_at | TIMESTAMPTZ | NOT NULL | 注册时间、管理员/个人主页排序 |
| updated_at | TIMESTAMPTZ | NOT NULL | 个人资料最近修改时间 |

表级约束：
```sql
CREATE UNIQUE INDEX user_email_lower_uniq ON app_user (lower(email));
-- 基础非空检查；不保证密码实际可用或 SSO 标识有效
ALTER TABLE app_user ADD CONSTRAINT user_login_method_chk
    CHECK (password <> '' OR sso_subject IS NOT NULL);
```

#### 设计细节

1. 内部主键用于关系与索引，对外使用随机 uid；随机标识不能代替对象权限，所有私有信息查询仍须鉴权。
2. `real_id` 使用字符串，保留兼容编号的前导零；新注册账号不要求提交学号/工号。
3. `is_active` 控制账号是否启用；停用账号不能继续建立或使用业务会话。
4. 保留 `sso_subject` 作为学校身份认证扩展字段；当前 HTTP 注册登录采用邮箱密码。
5. 认证凭证（SSO ticket、token 等）不落库、不写日志。
6. `user_login_method_chk` 仅校验基础非空关系。Django 的不可用密码也可能是非空字符串，因此该约束仅拦截密码为空且 SSO 标识为 NULL 的记录；认证流程仍须检查有效身份绑定，密码登录使用 `has_usable_password()` 检查，不能把该 CHECK 当作账号可登录的保证。
7. 业务管理员权限仅由 `is_admin` 决定，与展示身份 `role`、Django 管理字段 `is_staff` / `is_superuser` 分开。
   
### 1.2 Recruitment 招募信息表

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | 招募唯一标识 |
| publisher_id | BIGINT | NOT NULL，FK → app_user.id | 发布者的`id`字段 |
| title | VARCHAR(100) | NOT NULL | 招募名称（竞赛/活动名称） |
| type | VARCHAR(32) | NOT NULL，CHECK (type IN ('competition','activity','internship')) | 类型：competition(竞赛), activity(活动)， internship（实习） |
| description | TEXT | NOT NULL | 需求描述与补充说明 |
| min_headcount | INT | 可空；非空时 `1 <= min_headcount <= max_headcount` | 预期人数下限，仅用于展示；发布时只填单个整数则为 NULL |
| max_headcount | INT | NOT NULL，`>= 1` | 人数上限，满员判定以它为准 |
| accepted_count | INT | NOT NULL，默认 0，`0 <= accepted_count <= max_headcount`；删除时为 0 | 当前处于已接受状态的申请数 |
| status | VARCHAR(16) | NOT NULL，默认 'open'，CHECK (status IN ('open','full','closed')) | 状态：open(进行中), full(已满员), closed(已关闭) |
| deadline | TIMESTAMPTZ | NOT NULL | 截止时间 |
| closed_at | TIMESTAMPTZ | 可空 | 首次关闭生效时间；自动关闭取 deadline，手动关闭取操作时间；用于七天处理期，后续满员或删除不清空、不重置 |
| full_at | TIMESTAMPTZ | 可空 | 首次达到满员的时间；后续删除不清空、不重置 |
| close_reason | VARCHAR(16) | 可空，CHECK (close_reason IN ('deadline','manual')) | 关闭原因：到期自动关闭 / 发布者手动关闭 |
| deleted_at | TIMESTAMPTZ | 可空 | 软删除时间；常规招聘列表与详情排除已删除对象，授权申请历史仍可提供删除摘要 |
| application_status_counts | JSONB | 可空，默认 NULL | 旧聚合快照兼容字段，仅含 processing / accepted / rejected / withdrawn / invalid 五个键及非负整数；当前不调度明细清理 |
| applications_anonymized_at | TIMESTAMPTZ | 可空 | 旧清理完成时间兼容字段，当前不产生新的清理记录 |
| created_at | TIMESTAMPTZ | NOT NULL | 发布时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 最近修改时间 |

表级约束：
```sql
-- 已删除招聘的当前接受人数为零。
ALTER TABLE recruitment ADD CONSTRAINT recruitment_deleted_count_chk
    CHECK (deleted_at IS NULL OR accepted_count = 0);
-- 达到人数上限时必须为 full。
ALTER TABLE recruitment ADD CONSTRAINT recruitment_full_chk
    CHECK (accepted_count < max_headcount OR status = 'full');
-- 状态与时间字段对应
ALTER TABLE recruitment ADD CONSTRAINT recruitment_closed_time_chk
    CHECK (status <> 'closed' OR closed_at IS NOT NULL);
ALTER TABLE recruitment ADD CONSTRAINT recruitment_full_time_chk
    CHECK (status <> 'full' OR full_at IS NOT NULL);
-- 关闭时间与关闭原因同时存在或同时为空
ALTER TABLE recruitment ADD CONSTRAINT recruitment_close_pair_chk
    CHECK ((closed_at IS NULL) = (close_reason IS NULL));
-- 清理完成标记与统计计数同时存在
ALTER TABLE recruitment ADD CONSTRAINT recruitment_cleanup_pair_chk
    CHECK ((applications_anonymized_at IS NULL) = (application_status_counts IS NULL));
```

索引：
```sql
-- 列表页：按状态与发布时间倒序
CREATE INDEX recruitment_status_created_idx ON recruitment (status, created_at DESC) WHERE deleted_at IS NULL;
-- 我发布的招聘
CREATE INDEX recruitment_publisher_idx ON recruitment (publisher_id);
-- 定时任务扫描到期招聘
CREATE INDEX recruitment_deadline_idx ON recruitment (deadline) WHERE status = 'open' AND deleted_at IS NULL;
-- 定时任务扫描关闭满七天的招聘
CREATE INDEX recruitment_closed_at_idx ON recruitment (closed_at) WHERE status = 'closed' AND deleted_at IS NULL;
-- 定时任务扫描尚未清理申请明细的招聘；起算点为 LEAST(closed_at, full_at, deleted_at)，LEAST 忽略 NULL
CREATE INDEX recruitment_cleanup_idx ON recruitment (id)
    WHERE applications_anonymized_at IS NULL
      AND (closed_at IS NOT NULL OR full_at IS NOT NULL OR deleted_at IS NOT NULL);
-- 关键词搜索（title / description）：启用 pg_trgm 后建 GIN 索引，或使用 PostgreSQL 全文检索
```

#### 设计细节

1. `internship` 表示校内实验室实习。
2. 人数规则：支持正整数上限或闭区间，`1 <= min_headcount <= max_headcount <= 200`；下限可空。容量判断使用上界，编辑不得低于已接受人数，等于时原子触发满员。
3. 状态流转：
   - 到截止时间：`open → closed`（`close_reason='deadline'`，`closed_at=deadline`），不能投递新申请，已投递申请仍可处理（7 天内）；
   - 手动关闭：人数未达上限时可操作，`open → closed`（`close_reason='manual'`，`closed_at` 为操作时间），其余同上；
   - 达到人数上限：`open/closed → full`，记录 `full_at`，不能投递，也不能再接受；剩余处理中的申请自动拒绝并通知；
   - 两个状态同时触发时，优先标记为 `full`；若从 open 状态处理时截止时间也已到，仍补记 `closed_at=deadline` 与 `close_reason='deadline'`，但不覆盖最终的 full 状态；已有手动关闭时间与原因保持不变；
   - 已关闭状态下仅在 `now < closed_at + 7 天` 时允许发布者处理申请，每次接受都要校验人数，满员则转为 `full`；到达七天边界后，剩余处理中申请自动拒绝并通知，`decided_at` 取 `closed_at + 7 天`。七天限制同时适用于发布者处理及申请人修改、撤回；在锁内按当前时间复核，不依赖任务及时运行。
   - 状态不变量由 `recruitment_full_chk` 保证：`accepted_count == max_headcount` 的招聘必为 `full`，因此 `open` 状态一定未满员，手动关闭不需要另写“已满员”的特殊分支。调整上限使其等于 `accepted_count`（触发满员）时，必须在同一次 UPDATE 中同时写入 `status='full'` 与 `full_at`，否则违反 CHECK；其余处理中申请的自动拒绝在同一事务内随后执行。
4. 修改限制：仅未删除、未过截止时间且为 `open` 状态可修改；修改后截止时间必须晚于当前时间，上限不得小于 `accepted_count`。
5. 本人删除与治理删除分入口：本人操作要求发布者身份、open 且未过截止时间；管理员标记不绕过该限制。治理删除要求当前管理员及非空原因，可处置任何未删除状态。删除时在同一事务内将补执行后 processing/accepted 转为 invalid、accepted_count 归零，追加状态历史、通知与审计；rejected/withdrawn 不变。保留业务状态和历史时间，不重新开放。发布者对全部关联简历禁读，申请人仍可下载保留文件。
6. “截止时间晚于当前时间且不超过一年”依赖 `now()`，无法用 CHECK 表达，放在 Django 的 `clean()` / serializer 中校验。
7. 领域标签放在独立的 Tag 表（见 1.3），允许一个招聘挂多个标签。
8. 招聘类型预设取值较少，后续新增类型只需调整 CHECK 约束并做一次迁移，不影响身份与权限核心规则。
9. 长期保留申请及简历，不按固定 180 天期限隐藏或物理清理。`application_status_counts`、`applications_anonymized_at` 仅兼容既有聚合数据，不恢复已丢失明细；相关预留字段和索引保留。
10. `accepted_count` 应与当前已接受申请数一致，删除使有效申请失效时归零。`application_status_counts` 只表示旧聚合快照，不代替当前人数；申请状态历史记录后续真实流转，不回填无法证实的旧事件。

### 1.3 Tag 领域标签 与 RecruitmentTag联系表

Tag：预设的领域标签（计算机、设创……），尽量全覆盖，由开发者通过后台维护。

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | 标签标识 |
| name | VARCHAR(32) | NOT NULL, UNIQUE | 标签名称 |
| sort_order | INT | NOT NULL，默认 0 | 前端展示顺序 |
| is_active | BOOLEAN | NOT NULL，默认 TRUE | 是否可用（停用后不能再被选择，已有招聘不受影响） |

RecruitmentTag：招聘与标签的多对多关系（Django 中用 `ManyToManyField(Tag, through=...)` 或直接用默认中间表）。

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | |
| recruitment_id | BIGINT | NOT NULL，FK → recruitment.id | |
| tag_id | BIGINT | NOT NULL，FK → tag.id | |

表级约束：`UNIQUE (recruitment_id, tag_id)`；发布时至少选择一个标签（应用层校验）。



### 1.4 Application 申请表

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | 申请标识 |
| recruitment_id | BIGINT | NOT NULL，FK → recruitment.id | 所申请的招聘 |
| applicant_id | BIGINT | NOT NULL，FK → app_user.id | 申请人，长期保留业务归属关系 |
| resume_file | VARCHAR(255) | NOT NULL | 简历文件存储路径（`FileField`），文件不在公开静态目录下 |
| resume_name | VARCHAR(255) | NOT NULL | 原始文件名，仅用于展示 |
| resume_size | INT | NOT NULL，`<= 10485760` | 文件大小（字节），上限 10MB |
| resume_type | VARCHAR(8) | NOT NULL，CHECK (resume_type IN ('pdf','doc','docx')) | 文件格式 |
| note | TEXT | 可空 | 补充说明 |
| status | VARCHAR(16) | NOT NULL，默认 'processing'，CHECK (status IN ('processing','accepted','rejected','withdrawn','invalid')) | 状态：processing(处理中), accepted(已接受), rejected(已拒绝), withdrawn(已撤回), invalid(已失效) |
| publisher_mark | VARCHAR(16) | NOT NULL，默认 'none'，CHECK (publisher_mark IN ('none','hold')) | 发布者私有标记：none(未标记), hold(暂留)。仅发布者可见，申请人看不到 |
| has_unseen_update | BOOLEAN | NOT NULL，默认 FALSE | 申请人修改申请后置为 TRUE，发布者查看后置为 FALSE（小红点） |
| created_at | TIMESTAMPTZ | NOT NULL | 提交时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 最近修改时间 |
| decided_at | TIMESTAMPTZ | 可空 | 首次离开 processing 的时间（接受、拒绝、撤回、失效均算）；accepted → invalid 时保留原值。自动处理取业务时间，见 0 第 7 条。它不代表失效时间，失效时间见 `Recruitment.deleted_at` |

索引与约束：
```sql
-- processing 当且仅当尚未离开 processing，即 decided_at 为空
ALTER TABLE application ADD CONSTRAINT application_decided_chk
    CHECK ((status = 'processing') = (decided_at IS NULL));
-- 同一用户对同一招聘，未撤回的申请最多一条（接受/拒绝后也不能再投），撤回后可重投并生成全新记录
CREATE UNIQUE INDEX application_active_uniq
    ON application (recruitment_id, applicant_id)
    WHERE status <> 'withdrawn';
-- 发布者查看某招聘下的申请
CREATE INDEX application_recruitment_status_idx ON application (recruitment_id, status);
-- 我发出的申请
CREATE INDEX application_applicant_idx ON application (applicant_id, created_at DESC);
```

#### 设计细节

1. 状态机：`processing → accepted / rejected / withdrawn / invalid`。接受、拒绝、撤回后不能再进行常规处理；招聘删除时，允许 `accepted → invalid`。`decided_at` 仅在首次离开 processing 时写入，已接受后因删除失效不覆盖首次决定时间。processing → invalid 时 `decided_at` 取删除时刻，accepted → invalid 时保留首次决定时刻，因此查询“失效时间”一律读 `Recruitment.deleted_at`，不得读 `decided_at`。
2. “暂留”不是申请状态，而是发布者的私有标记（`publisher_mark='hold'`），此时 `status` 仍为 `processing`。
3. `invalid`（已失效）用于招聘被删除时，处理中与已接受的申请。已拒绝、已撤回的申请保持原状态。
4. 重投：撤回后重新投递会生成新记录；撤回的旧记录保留，这样就不会和部分唯一索引冲突。
5. 修改与撤回申请的条件：先在事务一补执行（0 第 7 条），再在事务二锁招聘、重新读取申请，要求申请仍为 `processing`、招聘未删除且当前仍在处理窗口内。加锁前读取申请只用来取得 `recruitment_id`，不用其状态作决定。招聘关闭后的七天内申请人仍可修改或撤回；到期自动拒绝后申请已不是 processing，自然不可再改。不按固定留存期限限制读取；状态处理与时间边界仍在锁内校验。
   修改申请：仅 `processing` 状态可修改，不限次数；修改操作写入 AuditLog，同时置 `has_unseen_update = TRUE` 并通知发布者。新文件先以独立存储名写入并校验；事务内锁招聘、重新校验申请状态后更新申请指向；事务提交成功后才删除旧文件；写入、校验或数据库事务失败时清理新文件。提交后若仅旧文件删除失败，不得清理已被申请引用的新文件，而应重试删除旧文件，最终不保留旧版本，禁止先覆盖或删除旧文件。首次提交同样先写入并校验文件，再事务内创建完整申请，失败时清理文件。文件清理失败须记录并重试；进程中断遗留的孤立文件由定时任务清理。新文件写入专用暂存前缀目录，清理只处理“未被任何 Application 引用且最后修改时间超过 24 小时”的文件；尚未提交的上传文件虽未被引用，但不满足年龄条件，不会被误删。上传请求超时上限须远小于 24 小时。
6. 长期留存：申请、简历不按固定期限过滤或清理；按业务关系及状态限制访问。已丢失的文件或被清理明细不自动恢复，不编造历史事件。
7. 申请人始终可查看本人记录及保留简历；发布者可查看关联申请，但撤回、失效或招聘删除后不得下载简历，补充说明及私有标记也不返回。招聘删除后的限制包含仍为 rejected 的申请；无关用户及管理员没有额外读取权。
8. 投递必须在 service 层事务内、锁住招聘后校验：申请人不是发布者、已确认个人信息处理告知、招聘未删除、状态为 open 且 `now < deadline`，并满足未重复投递及文件格式、大小要求。到期但状态尚未更新为 closed 时，同样禁止投递。
9. 接受申请分两个独立事务（见 0 第 7、8 条）：事务一调用 `sync_recruitment` 补执行到期状态流转并提交；事务二在同一事务内：锁招聘行 → 重新读取并校验申请仍为 processing、操作者为发布者、招聘未删除且未满员（open 须未截止，closed 须仍在七天处理期内）、`accepted_count < max_headcount` → 更新申请状态与首次 decided_at → `accepted_count + 1` → 若满员则置 full、写 full_at 并批量拒绝其余处理中申请，写入它们的 decided_at 和相应通知。重复接受同一申请不能再次增加人数。修改人数上限触发满员时，复用相同的满员处理逻辑。拒绝、暂留、撤回、修改和定时任务也必须遵循通用约定中的加锁顺序与状态复核。

### 1.5 Notification 站内通知

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | 通知标识 |
| recipient_id | BIGINT | NOT NULL，FK → app_user.id | 接收人 |
| type | VARCHAR(32) | NOT NULL | 通知类型，如 application_accepted / application_rejected / application_withdrawn / application_updated / recruitment_updated / recruitment_deleted / recruitment_closed / admin_removed |
| title | VARCHAR(100) | NOT NULL | 通知标题 |
| content | TEXT | NOT NULL | 通知内容，不含简历内容与申请者完整个人信息 |
| recruitment_id | BIGINT | 可空，FK → recruitment.id | 关联招聘，用于跳转 |
| application_id | BIGINT | 可空，FK → application.id | 关联申请，用于跳转 |
| announcement_id | BIGINT | 可空，FK → announcement.id | 关联公告，与招聘/申请关联互斥 |
| is_read | BOOLEAN | NOT NULL，默认 FALSE | 是否已读 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |

索引：`(recipient_id, is_read, created_at DESC)`。

#### 设计细节

1. 通知由统一的 service 生成，申请状态流转、招聘修改/删除/关闭、管理员删除都调用同一个入口，保证可复用。公告治理删除通知复用同一入口，关联 `announcement_id`，与招聘/申请关联互斥，见第 4 章 4.1。
2. 招聘采用软删除，删除时不级联删除通知。通知生成和所有读取/已读操作均不按固定期限过滤；物理清理仍属预留。通知不包含简历内容或申请人的完整身份。旧通知不重写正文、不补造缺失事件；无关联旧通知仍仅向接收人提供。
3. 申请事件通知，以及因招聘修改或删除失效而发给申请人的通知，均须同时填写 application_id 和 recruitment_id；同一用户存在撤回后重投的多条记录时，通知按业务规则关联相应申请并避免重复发送。给发布者本人的纯招聘通知可不关联 application_id。业务事件只生成站内通知：不再创建 `EmailLog(PENDING)`，不再挂接邮件派发回调；`email_notify_enabled` 保留为兼容字段，不控制发信；`email_log` 旧数据保留。
4. 创建时校验事件接收人：提交/修改/撤回申请通知发布者；处理结果、招聘修改及删除失效通知对应申请人；招聘关闭或治理删除通知发布者；公告治理通知作者。治理通知必须包含原因。读取、未读数和已读范围使用同一关联权限过滤，公告作者撤权不影响读取本人通知。
5. `target_is_deleted` 为响应时计算的布尔字段，不入库；取关联招聘/公告当前删除标记，无关联旧通知为 false，不代替申请状态与下载权限。查询预加载目标，不通过通知恢复已删除公开内容。
6. 业务锁和状态校验保证事件幂等；招聘内容与标签集合相同、申请说明相同且无新文件的更新不产生版本或通知。通知已读与申请修改的已阅版本彼此独立。迟到补执行的通知创建时间为实际时间，申请决定时间仍为业务边界。

### 1.6 EmailLog 邮件发送日志

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | |
| notification_id | BIGINT | NOT NULL，FK → notification.id | 对应的站内通知 |
| to_email | VARCHAR(254) | NOT NULL | 发送时的收件地址 |
| status | VARCHAR(16) | NOT NULL，默认 'pending'，CHECK (status IN ('pending','sent','failed')) | 发送状态 |
| attempts | INT | NOT NULL，默认 0，`0 <= attempts <= 3` | 当前发送轮次：首次为 0，第 1～3 次重试为 1～3；最多发送四次，见设计细节 3 |
| last_error | TEXT | 可空 | 最近一次失败原因 |
| created_at | TIMESTAMPTZ | NOT NULL | |
| updated_at | TIMESTAMPTZ | NOT NULL | |

#### 设计细节

1. 保留表结构和历史数据；当前业务事件不创建本表记录，`email_notify_enabled` 不触发发信。
2. `attempts`、状态及错误字段用于解释历史数据；邮件派发与重试命令仍为预留，后续启用须另行评审。
3. 保留历史邮件日志；如未来清理关联通知，须处理本表的 PROTECT 关系。错误日志不得保存简历内容、认证凭证或完整邮件正文。

### 1.7 ChatConversation 会话 与 ChatMessage 消息

聊天表结构独立于招聘与申请，仅定义两个参与者之间的纯文本消息；当前未提供聊天 HTTP 接口。

ChatConversation：

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | |
| user_low_id | BIGINT | NOT NULL，FK → app_user.id | 两个参与者中 id 较小者 |
| user_high_id | BIGINT | NOT NULL，FK → app_user.id | 两个参与者中 id 较大者 |
| last_message_at | TIMESTAMPTZ | 可空 | 最近一条消息时间，用于会话列表排序 |
| created_at | TIMESTAMPTZ | NOT NULL | |

表级约束：`CHECK (user_low_id < user_high_id)`，`UNIQUE (user_low_id, user_high_id)`，保证任意两人只有一个会话。

ChatMessage：

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | |
| conversation_id | BIGINT | NOT NULL，FK → chat_conversation.id | |
| sender_id | BIGINT | NOT NULL，FK → app_user.id | 必须是会话参与者（应用层校验） |
| content | TEXT | NOT NULL，长度 1~2000（应用层校验） | 纯文本 |
| created_at | TIMESTAMPTZ | NOT NULL | |
| read_at | TIMESTAMPTZ | 可空 | 对方已读时间 |

索引：`(conversation_id, created_at)`。

#### 设计细节

1. 管理员不可查看聊天记录，接口层不提供任何管理员读取聊天内容的入口。
2. 消息读取、发送与推送通道尚未对外提供，模型存在不代表聊天功能可用。

### 1.8 AuditLog 审计日志

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | |
| actor_id | BIGINT | 可空，FK → app_user.id | 操作者；未登录请求被拒绝时为 NULL，其余操作必填（应用层校验） |
| actor_role | VARCHAR(32) | 可空 | 操作时的基础身份（student / teacher）；`actor_id` 为 NULL 时同为 NULL |
| actor_is_admin | BOOLEAN | 可空 | 操作时是否以管理员权限执行；`actor_id` 为 NULL 时同为 NULL |
| action | VARCHAR(32) | NOT NULL | 动作，如 recruitment_delete / admin_delete / resume_view / application_update / permission_denied / announcement_publish / announcement_update / announcement_delete |
| target_type | VARCHAR(32) | NOT NULL | 对象类型，如 recruitment / application / announcement |
| target_id | BIGINT | 可空 | 对象 id；请求的对象不存在时为 NULL |
| reason | TEXT | 可空 | 原因（管理员删除时必填，在应用层校验） |
| created_at | TIMESTAMPTZ | NOT NULL | 操作时间 |

表级约束：`CHECK ((actor_id IS NULL) = (actor_role IS NULL) AND (actor_id IS NULL) = (actor_is_admin IS NULL))`。

索引：`(target_type, target_id)`，`(actor_id, created_at DESC)`。

#### 设计细节

1. 必须记录的操作：管理员权限的行使、用户删除本人发布的招聘、发布者查看申请人简历、申请人修改申请、权限被拒绝的请求、管理员发布公告，发布者编辑公告，发布者或管理员删除公告。
2. 日志自每条记录的 created_at 起至少保留一年；业务操作只追加，不提供修改与删除接口，当前不调度审计清理。审计留存独立于申请状态与招聘软删除，不因业务删除而提前删改。target_id 是无外键的历史对象标识，允许其目标因历史清理而不存在。
3. 日志中不写入认证凭证、简历内容、原始文件名、补充说明或申请人与招聘的额外映射；reason 仅记录必要的操作原因，不复制申请明细。申请清理后不另存已删除对象的快照或身份对照表。审计记录仍可能识别操作者，这是至少一年审计留存要求的明确例外，仅供授权审计使用，不作为普通申请查询入口。

### 1.9 Announcement 公告

对应需求 FR-09（竞赛与活动公告）。由管理员发布；作者（管理员）可编辑与本人删除，任一管理员可经治理入口删除并通知作者；所有已登录用户可查看列表和详情，并可通过关联的招募链接进入招募。

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | 公告标识 |
| author_id | BIGINT | NOT NULL，FK → app_user.id | 发布公告的管理员，PROTECT |
| title | VARCHAR(100) | NOT NULL | 竞赛/活动名称 |
| content | TEXT | NOT NULL | 公告正文，含报名方式等其他相关信息 |
| time_kind | VARCHAR(16) | NOT NULL，CHECK (time_kind IN ('deadline','event')) | 时间类型：deadline(报名截止时间), event(活动时间) |
| event_at | TIMESTAMPTZ | NOT NULL | 与 time_kind 对应的时间值 |
| link_url | VARCHAR(500) | 可空 | 相关网站；格式由应用层校验 |
| recruitment_id | BIGINT | 可空，FK → recruitment.id | 关联的招募（招募链接）；为空表示纯文字公告，PROTECT |
| is_pinned | BOOLEAN | NOT NULL，默认 FALSE | 是否置顶；HTTP 不提供置顶能力、不参与排序，仅保留字段 |
| created_at | TIMESTAMPTZ | NOT NULL | 发布时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 最近编辑时间 |
| deleted_at | TIMESTAMPTZ | 可空 | 软删除时间；非空表示已删除，不在任何列表和详情中出现 |

表级约束：
```sql
ALTER TABLE announcement ADD CONSTRAINT announcement_time_kind_chk
    CHECK (time_kind IN ('deadline','event'));
```

索引：
```sql
-- 公告列表：置顶优先，再按发布时间倒序；仅含未删除公告
CREATE INDEX announcement_list_idx ON announcement (is_pinned DESC, created_at DESC) WHERE deleted_at IS NULL;
-- 某招募被哪些公告引用
CREATE INDEX announcement_recruitment_idx ON announcement (recruitment_id) WHERE recruitment_id IS NOT NULL;
```

#### 设计细节

1. 权限（均为应用层校验，不看 `is_staff`；未登录用户一律不可查看；业务服务在行锁内复核当前权限）：
   - 发布：当前 `is_admin` 用户；
   - 编辑与本人删除：当前 `is_admin` 且 `author_id` 等于当前用户，其他管理员也不能编辑；
   - 治理删除：当前 `is_admin` 用户，独立入口（`DELETE /admin/announcements/{id}`），与本人删除入口分离；
   - 置顶：数据库保留 `is_pinned` 字段，HTTP 不提供置顶能力（不可写、不参与排序），后续是否恢复见《修订说明与待确认事项》P-03；
   - 查看：已登录用户。
   - 公告作者被撤销管理员权限后，发布、编辑、本人删除与治理删除均被拒绝（含旧会话）。
2. 删除为软删除（设置 `deleted_at`）。本人删除不需要原因；治理删除原因必填，写入 AuditLog.reason，公告表不另设字段。
3. 发布、编辑、删除均写入 AuditLog：`action` 取 announcement_publish / announcement_update / announcement_delete，`target_type` 为 `announcement`；重复删除返回不存在/已删除结果，不重复写审计。
4. 列表按 `created_at DESC, id DESC` 稳定排序，不按 `is_pinned` 排序。
5. `event_at` 为带时区合法值即可，不限制必须晚于当前时间；已过时间不自动等于已删除，编辑不因历史时间被拒绝（《修订说明与待确认事项》2.3）；`title`、`content`、`time_kind`、`event_at` 为必填。
6. 正常发布、编辑、本人删除不生成站内通知和邮件。治理删除在同一业务事务内完成软删除、审计与作者站内通知（`announcement_admin_removed`，含公告名称、处置结果、原因与公告引用），不产生邮件任务。
7. `recruitment_id` 指向的招募被软删除、关闭或满员后，公告仍保留；公告详情以 `recruitment_available` 表达链接可用性（关联存在且未删除），已删除招募的公开详情不因公告恢复。写入时该招募须存在且未删除；业务删除不物理删除 Recruitment 行，不破坏本表关联。
8. 公告不属于 Recruitment 的子类型，不进入招募的列表、搜索和定时任务。

## 2 表关系概览

```
app_user 1 ──< recruitment            （发布）
app_user 1 ──< application            （申请）
recruitment 1 ──< application
recruitment >──< tag                  （通过 recruitment_tag）
app_user 1 ──< notification ──< email_log
app_user >──< app_user                （通过 chat_conversation）
chat_conversation 1 ──< chat_message
app_user 1 ──< audit_log
app_user 1 ──< announcement    （管理员发布）
recruitment 1 ──< announcement        （可选，招募链接）
```

## 3 未提供的数据能力

当前未建立个性化推荐及举报处理模型；通用管理后台不属于已交付接口。

## 4 迁移与兼容

以下列出现有迁移的作用及兼容边界。申请、简历与通知不按固定期限隐藏；不执行物理清理，也不因取消过滤而补造已丢失历史。

### 4.1 通知的公告关联（`notifications.0002_notification_announcement_and_more`）

| 变更 | 内容 |
| --- | --- |
| 字段 | `notification.announcement_id`：BIGINT 可空，FK → announcement.id，PROTECT；与 `recruitment_id`、`application_id` 并列的第三种目标关联 |
| 互斥约束 | `announcement_id` 非空 ⇒ `recruitment_id`、`application_id` 均为空 |
| 一致性约束 | `application_id` 非空 ⇒ `recruitment_id` 非空（申请通知必须同时关联招聘） |
| 语义 | 公告治理删除通知（type=`announcement_admin_removed`）关联公告；与招聘/申请关联语义分开，旧通知数据保持兼容（新列为空） |
| 验证 | 迁移在空库与既有数据上均可应用；模型级约束测试（互斥与一致性各一正一反）；旧通知读取兼容测试；治理删除事务内通知与审计一致性测试 |

### 4.2 注册/登录失败计数表（`accounts.0002_authfailure`）

| 变更 | 内容 |
| --- | --- |
| 新表 | `auth_failure`：id BIGINT 自增主键，`key_hash` VARCHAR(64)（邮箱或 IP 的 SHA-256 摘要，不落明文）、`kind` VARCHAR(16)（login/register）、`created_at` TIMESTAMPTZ |
| 索引 | `(key_hash, created_at)` |
| 用途 | 失败限流：600 秒窗口内同邮箱键 5 次、同 IP 键 20 次；采用插入即计数（INSERT），无读改写，保证并发失败不丢计数；注册/登录分别计数，字段校验失败与业务认证失败各计一次，邮箱不可解析时仅计 IP；成功按对应操作的邮箱键删除计数，窗口外记录惰性清理 |
| 验证 | 并发失败计数一致性测试；窗口滑过自动恢复；成功登录清零；键只保存摘要，不存原始邮箱 |

受控管理员授予/撤销和历史密码初始化复用 `app_user`，锁定目标行后将账号变更与审计同事务提交；失败整体回滚。密码初始化拒绝覆盖已有可用密码，注册与初始化统一校验 8～128 字符及邮箱、姓名相似度；无新增密码重置接口或数据表。

### 4.3 申请状态变更历史表（`applications.0002_stage4_rules`）

| 变更 | 内容 |
| --- | --- |
| 新表 | `application_status_history`：id 自增主键；`application_id` FK → application（PROTECT）；`recruitment_id` FK → recruitment（PROTECT）；`from_status`、`to_status` VARCHAR(16)；`reason` VARCHAR(32)（accept / reject_manual / withdraw / auto_full / auto_window / delete_invalid）；`actor_id` 可空 FK → app_user（空表示系统来源）；`occurred_at` TIMESTAMPTZ 为业务生效时间，`created_at` 为实际记录时间 |
| 覆盖 | 接受、拒绝、撤回、满员自动拒绝、超时自动拒绝、删除失效；暂留不改变状态不入史。允许的状态/原因组合、操作者来源由 CHECK 约束，同一申请的相同流转由 UNIQUE 防重。 |
| 边界 | 旧记录如无历史行，属于证据边界，不补写、不编造历史事件；`decided_at` 语义不变（失效时间仍取 `Recruitment.deleted_at`） |
| 验证 | 每种状态流转各写一条的单测；并发接受/撤回竞争下历史与状态一致；删除后 `accepted_count=0` 可由历史追溯 |

### 4.4 历史已删除招聘的人数修复（`recruitments.0003_stage4_rules`）

| 变更 | 内容 |
| --- | --- |
| 问题 | 历史数据中存在已软删除但 `accepted_count` 未归零的招聘统计值，与 FR-05「删除后为零」不符 |
| 修复 | 幂等数据迁移，在添加删除人数 CHECK 前执行：将 `deleted_at IS NOT NULL AND accepted_count <> 0` 的行置零；迁移仅修改计数，不改写状态和时间；反向迁移不推断或恢复未知旧统计 |
| 边界 | 只修复统计值，不改写业务状态与历史时间；不因人数归零重新开放招聘；无法还原的历史处理结果按 4.3 标注证据边界 |
| 验证 | 迁移回归验证只修复已删除行，保留正常行、业务状态与时间；重复迁移不重开招聘，不生成虚构历史事件 |
