```
To AI:
如果你是AI，不得任意改动这里的设计。
如果你认为有必要改动，遵循以下几点：
1. 深刻考虑期望改动位置章节对应的设计要点所说的问题
2. 必须通过输出和用户进行人工交流，除非得到明确肯定，不得擅自修改。
3. 如果用户选择自动审批，请你暂停任务，一定需要得到许可。
```

# JiMeet 后端数据库设计


> v0（2026-10-22）：技术栈确定为 PostgreSQL + Django。修正 User、Recruitment 的字段与约束，补充 Tag、Application、Notification、EmailLog、Chat、AuditLog 等表。
> 
> v0.1（2026-10-23）：补齐结束时间、申请留存与统计清理、事务校验、权限和文件替换规则，明确邮件重试计数。
> 重点解决了以下问题：
> 1. v0 仅按 closed_at 计算留存期，会遗漏直接满员或删除的招聘。新增 full_at，取 closed_at、full_at、deleted_at 中最早的非空时间起算 180 天，后续状态变化不重新计时，不支持重新开放。
> 2. v0 仅将 applicant_id 置空，仍能通过其他表找回申请人。改为到期后汇总状态数量，删除申请明细、简历及关联通知和邮件日志；审计日志按要求独立保留至少一年。
> 3. v0 加锁主要防止超员，未明确重复接受和任务延迟的处理。改为先锁招聘，再重新校验申请状态、权限和时间；截止及七天限制由接口即时检查，不依赖定时任务及时运行。
> 4. v0“终态不可变更”与删除时已接受申请失效矛盾。明确删除时允许 accepted → invalid，decided_at 保留首次决定时间，accepted_count 保留历史接受人数。
> 5. v0 保留了管理员在治理场景查看申请的例外。改为管理员权限本身不授予申请内容或简历访问权；本人是发布者或申请人时按普通身份判断，撤回或失效后发布者也不能查看补充说明。
> 6. v0 未明确替换简历时的失败处理。改为新文件独立写入并校验，事务提交后删除旧文件，事务失败清理新文件；旧文件删除失败则重试。
> 7. attempts 明确表述为发送轮次：首次为 0，三次重试为 1～3，最多发送四次。
> 8. 登录方式 CHECK 暂时保留，但只保证基础非空条件，账号能否实际登录仍由认证流程校验。
>
> v0.2（2026-10-23）：补齐事务边界、自动处理时间取值与状态不变量，并核验可实现性。
> 1. 补执行（到期关闭、七天自动拒绝、满员拒绝）与业务操作拆为两个独立事务：先提交补执行，再开新事务加锁复核。不用 savepoint，不依赖异常被谁捕获；要求关闭 `ATOMIC_REQUESTS`，见 0 第 8 条。
> 2. 自动处理的 `decided_at` 取业务时间而非任务运行时间：七天到期取 `closed_at + 7 天`，满员拒绝取 `full_at`，与“到期关闭取 deadline”同一原则。
> 3. 申请可修改/撤回的条件统一为“补执行后仍为 processing 且招聘未删除”；七天处理期只约束发布者处理，不约束申请人。
> 4. 新增 Recruitment 状态不变量 CHECK：`accepted_count < max_headcount OR status = 'full'`，以及 closed/full 与时间字段的对应关系，让“手动关闭时已满员但仍是 open”的状态无法写入，不再依赖文字规则。
> 5. 孤立文件清理以“未被引用且修改时间超过 24 小时”为准，避开尚未提交的上传。
> 6. 明确 `decided_at` 不代表失效时间，失效时间见 `Recruitment.deleted_at`；补充定时任务扫描索引和 Application、Recruitment 的状态对应 CHECK。
>
> v0.3（2026-10-23）：最终一致性核查，仅修正文档内部的矛盾与遗漏，不改变业务规则。
> 1. 1.4 设计细节 9（接受申请）仍写着“同一事务内先补执行”，与 0 第 7、8 条及 v0.2 第 1 条冲突。改为两个独立事务：事务一 `sync_recruitment` 提交，事务二锁招聘并复核后接受。
> 2. AuditLog 需记录“权限被拒绝的请求”，但 `actor_id`、`target_id` 为 NOT NULL，未登录请求和对象不存在的请求无法入库。两者改为可空，`actor_role`、`actor_is_admin` 随 `actor_id` 同为空或同非空，并新增表级 CHECK；其余操作的操作者必填由应用层校验。
> 3. 0 第 3 条要求枚举字段加 CHECK，但 `Notification.type`、`AuditLog.action` 没有。保持设计不变，在 0 第 3 条注明这两个有意不加 CHECK 的例外。
>
> 个性化推送、举报功能后续再加，本版不建表（Django 加表成本低，可随时迁移补上）。
> 
>

## 0 通用约定
1. 数据库：PostgreSQL；ORM：Django。表字段中的类型以 PostgreSQL 为准，括号内为 Django 对应写法。
2. 时间字段一律使用 `TIMESTAMPTZ`（`DateTimeField`，`USE_TZ = True`），不使用无时区的 DATETIME。
3. 枚举类字段（role、type、status 等）使用 `VARCHAR` + `CHECK` 约束（Django 中用 `TextChoices` + `CheckConstraint`），不使用 PostgreSQL 的 ENUM 类型，后续新增取值时迁移更简单。例外：`Notification.type`（1.5）和 `AuditLog.action`（1.8）取值会随功能频繁新增，有意不加 CHECK，由应用层常量约束。
4. 外键默认 `ON DELETE PROTECT`，业务上的“删除”一律为软删除或状态变更，避免误删申请记录（申请记录需保留 180 天）；留存期满后的后台清理是例外，按 1.4 显式清理依赖记录后物理删除明细。
5. 招聘的修改、关闭、删除，以及申请的提交、修改、撤回、处理和自动处理，统一在事务中先用 `select_for_update()` 锁住对应的 Recruitment 行，再重新读取申请并校验当前状态、权限、删除标记和时间窗口；不得使用加锁前读取的状态作决定。需要锁申请行时，一律先锁招聘、再锁申请，防止并发重复接受、接受与撤回冲突及超员。状态变更、人数更新、站内通知与邮件待发送记录在同一事务内保存，邮件在事务提交后发送。
6. 需要由定时任务驱动的逻辑（Celery beat，或 management command + cron）：
   - 到截止时间，招聘自动置为已关闭；
   - 招聘关闭满 7 天，仍处理中的申请自动拒绝并通知；
   - 招聘结束满 180 天后，按 1.2 的起算规则执行 1.4 的申请统计与明细清理；
   - 邮件发送失败重试；
   - 清理上传或替换失败遗留的孤立文件，重试未完成的申请明细清理。
7. 定时任务不作为权限和时间校验的唯一保障。相关接口使用当前时间判断是否到期；必要时先补执行到期关闭或七天到期自动拒绝，再判断请求。补执行的状态、通知必须提交，即使原请求已不符合操作条件，也不能因业务拒绝而将补执行回滚。实现方式固定为两个独立事务：
   - 事务一：`sync_recruitment(recruitment_id)`，锁招聘行，按当前时间补执行到期关闭、七天自动拒绝、满员拒绝，通知与邮件待发送记录一并写入，然后提交；
   - 事务二：业务操作，重新锁招聘行，重新读取申请并复核，再执行并提交。事务二里的业务拒绝只回滚事务二。
   - 不使用 savepoint 包住补执行：这要求每一层都正确捕获业务异常，外层多包一层 atomic 就会让补执行整体回滚。
   定时任务只调用 `sync_recruitment`，与接口共用同一套状态流转。仅实际发生状态变更时生成通知，重复执行不得重复计数或通知。同一次请求内取一次当前时间并复用，避免前后判断不一致。
   自动处理使用业务时间而非任务实际运行时间：到期关闭取 `closed_at = deadline`；七天到期自动拒绝的 `decided_at` 取 `closed_at + 7 天`；满员触发的自动拒绝取 `full_at`。任务延迟不改变这些时间，通知的 `created_at` 仍是真实创建时间。
8. 事务实现约束：Django 设置 `ATOMIC_REQUESTS = False`（默认值），由 service 层显式开启事务；service 入口不得嵌在调用方的外层 `atomic` 中，否则第 7 条的“先提交补执行”无法成立。涉及加锁、并发和补执行的测试使用 `TransactionTestCase`，不用被外层事务包住的 `TestCase`。邮件发送放在 `transaction.on_commit` 中，进程在提交后崩溃时依靠已提交的 pending 记录重试。

## 1 实体及其字段定义
### 1.1 User 用户
Django 实现：继承 `AbstractBaseUser` + `PermissionsMixin`，`USERNAME_FIELD = "real_id"`（或 email，视最终登录方式定），`db_table = "app_user"`（`user` 是 PostgreSQL 保留字，避免每次都要加引号）。管理员权限只使用 `is_admin`，不与 Django 自带的 `is_staff` / `is_superuser` 混用（后两者仅用于 Django Admin 后台，由开发者持有）。

| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY, 自增 | 数据库内的自增标识，不会对外公开 |
| uid | VARCHAR(32) | NOT NULL, UNIQUE | 对外使用的的uid，随机生成（`uuid4().hex`，恰好 32 位），防止被遍历爬取|
| real_id | VARCHAR(32) | NOT NULL, UNIQUE | 真实的学号/工号，内部使用，不对外公开|
| nickname | VARCHAR(32)  | NOT NULL | 可以自主定义的用户名 |
| name | VARCHAR(32)  | NOT NULL | 真实的姓名 |
| email | VARCHAR(254) | NOT NULL（必须是同济邮箱格式） | 邮箱号，用于登录预留与邮件通知 |
| role | VARCHAR(32)  | NOT NULL，CHECK (role IN ('student','teacher')) | 用户角色，只能是`student` 或 `teacher`，登录时依据学号/工号判定 |
| is_admin | BOOLEAN | NOT NULL，默认 FALSE | 是否拥有管理员权限 |
| is_active | BOOLEAN | NOT NULL，默认 TRUE | 是否启用 |
| password | VARCHAR(128) | NOT NULL DEFAULT '' | Django 哈希格式密码。“邮箱登录”预留；若只走统一身份认证则保持空串 |
| sso_subject | VARCHAR(191) | UNIQUE，可空 | 统一身份认证返回的稳定用户标识；与密码登录可并存 |
| email_notify_enabled | BOOLEAN | NOT NULL，默认 TRUE | 是否接收邮件通知（站内通知始终生成） |
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
1. 两个uid，原因是规格说明要求**任何接口不得通过遍历用户标识获取他人简历**，所以外部暴露uid不能是有序的，但是内部有序是有利于性能优化的
2. **因为工号确实存在0打头的情况，real_id被设置为VARCHAR。**
3. `is_active`在Django中可以很方便的实现封禁功能
4. `sso_subject` 与 `password` 两个字段略有冗余，但是为了后续简单，我认为有必要保留两个字段
5. 认证凭证（SSO ticket、token 等）不落库、不写日志。
6. 暂保留 `user_login_method_chk`。Django 的不可用密码也可能是非空字符串，因此该约束仅拦截密码为空且 SSO 标识为 NULL 的记录；认证流程仍须检查有效身份绑定，密码登录启用时使用 `has_usable_password()` 检查，不能把该 CHECK 当作账号可登录的保证。
7. 管理员与基础身份分离：`role` 表示学生/教师，`is_admin` 是附加权限，二者互不影响。因为有的学生也可以是管理员。
   
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
| accepted_count | INT | NOT NULL，默认 0，`0 <= accepted_count <= max_headcount` | 历史累计接受人数；删除招聘使申请失效时不递减，也不因申请明细清理而改变 |
| status | VARCHAR(16) | NOT NULL，默认 'open'，CHECK (status IN ('open','full','closed')) | 状态：open(进行中), full(已满员), closed(已关闭) |
| deadline | TIMESTAMPTZ | NOT NULL | 截止时间 |
| closed_at | TIMESTAMPTZ | 可空 | 首次关闭生效时间；自动关闭取 deadline，手动关闭取操作时间；用于七天处理期，后续满员或删除不清空、不重置 |
| full_at | TIMESTAMPTZ | 可空 | 首次达到满员的时间；后续删除不清空、不重置 |
| close_reason | VARCHAR(16) | 可空，CHECK (close_reason IN ('deadline','manual')) | 关闭原因：到期自动关闭 / 发布者手动关闭 |
| deleted_at | TIMESTAMPTZ | 可空 | 软删除时间；非空表示已被发布者或管理员删除，不在任何列表出现 |
| application_status_counts | JSONB | 可空，默认 NULL | 180 天后清理申请明细时保存的状态计数，仅含 processing / accepted / rejected / withdrawn / invalid 五个键及非负整数；见 1.4 |
| applications_anonymized_at | TIMESTAMPTZ | 可空 | 申请文件、明细及其关联通知、邮件日志完成清理的时间 |
| created_at | TIMESTAMPTZ | NOT NULL | 发布时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 最近修改时间 |

表级约束：
```sql
-- 状态不变量：达到上限必为 full。把“accepted_count 等于上限但仍是 open”的状态挡在数据库外
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
1. internship（实习）是指实验室实习，不是校外实习！请不要因为这个问题浪费宝贵的token。
2. 人数规则：因为需求中说发布时可填一个整数（只设 `max_headcount`），或一个闭区间（`min_headcount`~`max_headcount`，下限仅展示）。上限不得小于 `accepted_count`，可以等于并触发满员逻辑。
3. 状态流转：
   - 到截止时间：`open → closed`（`close_reason='deadline'`，`closed_at=deadline`），不能投递新申请，已投递申请仍可处理（7 天内）；
   - 手动关闭：人数未达上限时可操作，`open → closed`（`close_reason='manual'`，`closed_at` 为操作时间），其余同上；
   - 达到人数上限：`open/closed → full`，记录 `full_at`，不能投递，也不能再接受；剩余处理中的申请自动拒绝并通知；
   - 两个状态同时触发时，优先标记为 `full`；若从 open 状态处理时截止时间也已到，仍补记 `closed_at=deadline` 与 `close_reason='deadline'`，但不覆盖最终的 full 状态；已有手动关闭时间与原因保持不变；
   - 已关闭状态下仅在 `now < closed_at + 7 天` 时允许发布者处理申请，每次接受都要校验人数，满员则转为 `full`；到达七天边界后，剩余处理中申请自动拒绝并通知，`decided_at` 取 `closed_at + 7 天`。七天限制针对发布者处理，不限制申请人对仍为 processing 的申请修改或撤回；因为到期会被自动拒绝，实际可修改窗口在补执行后自然收敛，见 1.4 设计细节 5。
   - 状态不变量由 `recruitment_full_chk` 保证：`accepted_count == max_headcount` 的招聘必为 `full`，因此 `open` 状态一定未满员，手动关闭不需要另写“已满员”的特殊分支。调整上限使其等于 `accepted_count`（触发满员）时，必须在同一次 UPDATE 中同时写入 `status='full'` 与 `full_at`，否则违反 CHECK；其余处理中申请的自动拒绝在同一事务内随后执行。
4. 修改限制：仅未删除、未过截止时间且为 `open` 状态可修改；修改后截止时间必须晚于当前时间，上限不得小于 `accepted_count`。
5. 删除限制：仅未删除、未过截止时间且为 `open` 状态时发布者可删除，管理员不限招聘状态。删除即设置 `deleted_at`，同时把该招聘下状态为处理中、已接受的申请置为 `invalid`，关闭简历访问权限；已拒绝、已撤回的申请保持原状态。`accepted_count` 保留历史累计接受人数，不归零；删除后的招聘不再按它判断可接受人数。删除为软删除，申请按统一留存期保留；清理期满后也不得重新生成关联申请的通知。
6. “截止时间晚于当前时间且不超过一年”依赖 `now()`，无法用 CHECK 表达，放在 Django 的 `clean()` / serializer 中校验。
7. 领域标签放在独立的 Tag 表（见 1.3），允许一个招聘挂多个标签。
8. 招聘类型预设取值较少，后续新增类型只需调整 CHECK 约束并做一次迁移，不影响身份与权限核心规则。
9. 申请留存起算点取 `closed_at`、`full_at`、`deleted_at` 中最早的非空时间，从该时刻保留 180 天。直接满员从满员时间算，直接删除从删除时间算，关闭后满员或管理员再删除均不重新计时。截止后才执行删除等操作时，若招聘仍为 open，先补记 `closed_at=deadline` 及关闭原因，避免任务延迟改变起算点；已满员、已关闭或已删除的招聘不再补记新的关闭时间。三个时间在各自事件发生后不得重置；不支持重新开放招聘。到期清理后不再展示个人申请明细，仅保留状态计数。
10. `accepted_count` 在未删除且申请明细尚未清理时，应等于 accepted 状态的申请数量；删除使其失效后仍保留原值。`application_status_counts` 则统计清理当时的实际状态，因此其 accepted 计数在删除后可能为 0，与历史累计接受人数含义不同。

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
| applicant_id | BIGINT | NOT NULL，FK → app_user.id | 申请人；180 天后删除申请明细，因此保持 NOT NULL，无需置空 |
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
5. 修改与撤回申请的条件：先在事务一补执行（0 第 7 条），再在事务二锁招聘、重新读取申请，要求申请仍为 `processing` 且招聘未删除。加锁前读取申请只用来取得 `recruitment_id`，不用其状态作决定。招聘关闭后的七天内申请人仍可修改或撤回；到期自动拒绝后申请已不是 processing，自然不可再改。留存期条件是上述条件的推论（处理中的申请最迟在关闭满七天或删除时已离开 processing），不另作判断。
   修改申请：仅 `processing` 状态可修改，不限次数；修改操作写入 AuditLog，同时置 `has_unseen_update = TRUE` 并通知发布者。新文件先以独立存储名写入并校验；事务内锁招聘、重新校验申请状态后更新申请指向；事务提交成功后才删除旧文件；写入、校验或数据库事务失败时清理新文件。提交后若仅旧文件删除失败，不得清理已被申请引用的新文件，而应重试删除旧文件，最终不保留旧版本，禁止先覆盖或删除旧文件。首次提交同样先写入并校验文件，再事务内创建完整申请，失败时清理文件。文件清理失败须记录并重试；进程中断遗留的孤立文件由定时任务清理。新文件写入专用暂存前缀目录，清理只处理“未被任何 Application 引用且最后修改时间超过 24 小时”的文件；尚未提交的上传文件虽未被引用，但不满足年龄条件，不会被误删。上传请求超时上限须远小于 24 小时。
6. 数据保留与匿名化：
   - 按 1.2 设计细节 9 保留申请明细 180 天。为满足“仅保留统计聚合值”，到期后删除明细，不采用仅置空 applicant_id 的方案；因此申请人、文件元数据和补充说明字段继续按正常申请定义，无需为匿名化改为可空。
   - 从到期时刻起，接口不再返回相关申请内容、文件或关联通知，也不再发送关联邮件，不依赖清理任务已运行。
   - 清理任务先按通用约定补执行应有的关闭和自动拒绝，确保无遗留 processing 申请，再删除所有关联简历文件（不存在视为成功）；全部成功后，在锁住招聘的事务内，按五种状态汇总数量到 `Recruitment.application_status_counts`，显式先删除关联通知的 EmailLog、再删除 Notification、最后删除全部 Application（包括撤回的旧记录），并写入 `applications_anonymized_at`。关联通知包括 application_id 指向这些申请的通知，以及 recruitment_id 指向该招聘且属于申请事件的通知；申请事件通知统一使用 `application_` 类型前缀。若失败则重试，完成标记与计数在同一事务中写入，重复任务不得覆盖已完成统计。
   - 不保存申请 id、申请人、精确提交时间等明细到统计字段，也不在通知正文或清理日志中另存这些明细。审计日志是独立的留存例外：按 1.8 至少保留一年，不声称全系统在 180 天时已不可识别。聊天记录不属于申请留存范围，也不作为申请身份映射存储。
7. 申请内容与简历权限：管理员权限本身不授予申请内容或简历的访问权；管理员本人若恰好是发布者或申请人，则按其普通用户身份判断。未到留存期限时，仅申请人本人、该招聘发布者可访问，且 withdrawn / invalid 状态不向任何人返回简历文件；发布者也不能查看这两种状态下的补充说明。申请详情、文件元数据和下载接口须使用一致的对象权限校验；到留存期限后双方均不能访问申请内容和文件。文件下载必须经过带权限校验的接口，不得暴露直链，也不得提供通过遍历用户标识获取他人简历的入口。
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
| is_read | BOOLEAN | NOT NULL，默认 FALSE | 是否已读 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |

索引：`(recipient_id, is_read, created_at DESC)`。

#### 设计细节
1. 通知由统一的 service 生成，申请状态流转、招聘修改/删除/关闭、管理员删除都调用同一个入口，保证可复用。
2. 招聘采用软删除，删除时不级联删除通知。申请相关通知保留至该招聘的 180 天申请留存期满，届时按 1.4 显式清理；其他招聘通知保留，但不得包含申请明细或申请人与申请的身份映射。
3. 申请事件通知，以及因招聘修改、关闭、删除而发给申请人的通知，均须同时填写 application_id 和 recruitment_id，便于到期清理；同一用户存在撤回后重投的多条记录时，通知按业务规则关联相应申请并避免重复发送。给发布者本人的纯招聘通知可不关联 application_id。同一事务内按用户邮件开关创建对应邮件待发送记录。邮件任务发送前重新检查通知是否存在、是否已到申请留存期限，与清理任务协调，不能在清理完成后继续从旧任务载荷发送申请邮件。

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
1. 仅在 `User.email_notify_enabled = TRUE` 时才创建记录。
2. 邮件正文只包含状态变更类型、关联信息名称、当前状态与站内链接。
3. `attempts` 表示发送轮次而非累计发送次数。记录创建及首次发送时为 0；失败且 attempts < 3 时，下一次重试发送前加 1；第 3 次重试仍失败时标记 failed。任意一次成功均标记 sent，不再重试。待发送与可重试期间保持 pending，最近错误写 last_error；任务需互斥处理同一条记录，防止并发重复发送。连续失败需要触发告警（运维需求）。
4. 关联申请到留存期限后停止发送；清理关联通知前显式删除本表记录，以满足默认 PROTECT 外键约束。错误日志不得保存简历内容、认证凭证或完整邮件正文。

### 1.7 ChatConversation 会话 与 ChatMessage 消息
聊天不依赖招聘与申请，任意两个用户都可以发起，仅支持纯文本。

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
2. 第一版可用轮询取消息，后续再升级为 Django Channels / WebSocket，表结构不变。

### 1.8 AuditLog 审计日志
| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | |
| actor_id | BIGINT | 可空，FK → app_user.id | 操作者；未登录请求被拒绝时为 NULL，其余操作必填（应用层校验） |
| actor_role | VARCHAR(32) | 可空 | 操作时的基础身份（student / teacher）；`actor_id` 为 NULL 时同为 NULL |
| actor_is_admin | BOOLEAN | 可空 | 操作时是否以管理员权限执行；`actor_id` 为 NULL 时同为 NULL |
| action | VARCHAR(32) | NOT NULL | 动作，如 recruitment_delete / admin_delete / resume_view / application_update / permission_denied |
| target_type | VARCHAR(32) | NOT NULL | 对象类型，如 recruitment / application |
| target_id | BIGINT | 可空 | 对象 id；请求的对象不存在时为 NULL |
| reason | TEXT | 可空 | 原因（管理员删除时必填，在应用层校验） |
| created_at | TIMESTAMPTZ | NOT NULL | 操作时间 |

表级约束：`CHECK ((actor_id IS NULL) = (actor_role IS NULL) AND (actor_id IS NULL) = (actor_is_admin IS NULL))`。

索引：`(target_type, target_id)`，`(actor_id, created_at DESC)`。

#### 设计细节
1. 必须记录的操作：管理员权限的行使、用户删除本人发布的招聘、发布者查看申请人简历、申请人修改申请、权限被拒绝的请求。
2. 日志自每条记录的 created_at 起至少保留一年；业务操作只追加，不提供修改与删除接口。后台留存清理任务仅可删除已满一年的日志。申请明细在 180 天后清理时，审计记录按本规则独立保留，不能为了宣称匿名化提前删改审计。target_id 是无外键的历史对象标识，对应申请明细删除后允许目标不存在。
3. 日志中不写入认证凭证、简历内容、原始文件名、补充说明或申请人与招聘的额外映射；reason 仅记录必要的操作原因，不复制申请明细。申请清理后不另存已删除对象的快照或身份对照表。审计记录仍可能识别操作者，这是至少一年审计留存要求的明确例外，仅供授权审计使用，不作为普通申请查询入口。

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
```

## 3 本版暂不建表（后续按需追加）
1. 个性化推送（用户兴趣、权重）：第一版推送可直接按时间排序，需要时再加。
2. 举报与管理员处理页面：需求整理建议后期添加。
