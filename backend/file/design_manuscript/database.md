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
> 个性化推送、举报功能后续再加，本版不建表（Django 加表成本低，可随时迁移补上）。
>

## 0 通用约定
1. 数据库：PostgreSQL；ORM：Django。表字段中的类型以 PostgreSQL 为准，括号内为 Django 对应写法。
2. 时间字段一律使用 `TIMESTAMPTZ`（`DateTimeField`，`USE_TZ = True`），不使用无时区的 DATETIME。
3. 枚举类字段（role、type、status 等）使用 `VARCHAR` + `CHECK` 约束（Django 中用 `TextChoices` + `CheckConstraint`），不使用 PostgreSQL 的 ENUM 类型，后续新增取值时迁移更简单。
4. 外键默认 `ON DELETE PROTECT`，业务上的“删除”一律为软删除或状态变更，避免误删申请记录（申请记录需保留 180 天）。
5. 涉及“招聘人数”与“申请状态”的修改，必须在事务中执行，并用 `select_for_update()` 锁住对应的 Recruitment 行，防止并发接受导致超员。
6. 需要由定时任务驱动的逻辑（Celery beat，或 management command + cron）：
   - 到截止时间，招聘自动置为已关闭；
   - 招聘关闭满 7 天，仍处理中的申请自动拒绝并通知；
   - 招聘关闭满 180 天后，申请记录匿名化；
   - 邮件发送失败重试。

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
-- 避免创建出永远登不进来的账号
ALTER TABLE app_user ADD CONSTRAINT user_login_method_chk
    CHECK (password <> '' OR sso_subject IS NOT NULL);
```

#### 设计细节
1. 两个uid，原因是规格说明要求**任何接口不得通过遍历用户标识获取他人简历**，所以外部暴露uid不能是有序的，但是内部有序是有利于性能优化的
2. **因为工号确实存在0打头的情况，real_id被设置为VARCHAR。**
3. `is_active`在Django中可以很方便的实现封禁功能
4. `sso_subject` 与 `password` 两个字段略有冗余，但是为了后续简单，我认为有必要保留两个字段
5. 认证凭证（SSO ticket、token 等）不落库、不写日志。
6. 管理员与基础身份分离：`role` 表示学生/教师，`is_admin` 是附加权限，二者互不影响。因为有的学生也可以是管理员。
   
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
| accepted_count | INT | NOT NULL，默认 0，`0 <= accepted_count <= max_headcount` | 已同意人数 |
| status | VARCHAR(16) | NOT NULL，默认 'open'，CHECK (status IN ('open','full','closed')) | 状态：open(进行中), full(已满员), closed(已关闭) |
| deadline | TIMESTAMPTZ | NOT NULL | 截止时间 |
| closed_at | TIMESTAMPTZ | 可空 | 进入 closed 状态的时间，用于“关闭后 7 天内可继续处理申请”的计时 |
| close_reason | VARCHAR(16) | 可空，CHECK (close_reason IN ('deadline','manual')) | 关闭原因：到期自动关闭 / 发布者手动关闭 |
| deleted_at | TIMESTAMPTZ | 可空 | 软删除时间；非空表示已被发布者或管理员删除，不在任何列表出现 |
| created_at | TIMESTAMPTZ | NOT NULL | 发布时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 最近修改时间 |

索引：
```sql
-- 列表页：按状态与发布时间倒序
CREATE INDEX recruitment_status_created_idx ON recruitment (status, created_at DESC) WHERE deleted_at IS NULL;
-- 我发布的招聘
CREATE INDEX recruitment_publisher_idx ON recruitment (publisher_id);
-- 定时任务扫描到期招聘
CREATE INDEX recruitment_deadline_idx ON recruitment (deadline) WHERE status = 'open';
-- 关键词搜索（title / description）：启用 pg_trgm 后建 GIN 索引，或使用 PostgreSQL 全文检索
```

#### 设计细节
1. internship（实习）是指实验室实习，不是校外实习！请不要因为这个问题浪费宝贵的token。
2. 人数规则：因为需求中说发布时可填一个整数（只设 `max_headcount`），或一个闭区间（`min_headcount`~`max_headcount`，下限仅展示）。上限不得小于 `accepted_count`，可以等于并触发满员逻辑。
3. 状态流转：
   - 到截止时间：`open → closed`（`close_reason='deadline'`），不能投递新申请，已投递申请仍可处理（7 天内）；
   - 手动关闭：人数未达上限时可操作，`open → closed`（`close_reason='manual'`），其余同上；
   - 达到人数上限：`open/closed → full`，不能投递，也不能再接受；剩余处理中的申请自动拒绝并通知；
   - 两个状态同时触发时，优先标记为 `full`；
   - 已关闭状态下 7 天内每次接受都要校验人数，满员则转为 `full`，7 天后仍未满员，剩余处理中申请自动拒绝并通知。
4. 修改限制：仅 `open` 状态可修改；修改后截止时间必须晚于当前时间，上限不得小于 `accepted_count`。
5. 删除限制：仅 `open` 状态下发布者可删除，管理员不限状态。删除即设置 `deleted_at`，同时把该招聘下状态为处理中、已接受的申请置为 `invalid`，简历访问权限关闭。
6. “截止时间晚于当前时间且不超过一年”依赖 `now()`，无法用 CHECK 表达，放在 Django 的 `clean()` / serializer 中校验。
7. 领域标签放在独立的 Tag 表（见 1.3），允许一个招聘挂多个标签。
8. 招聘类型预设取值较少，后续新增类型只需调整 CHECK 约束并做一次迁移，不影响身份与权限核心规则。

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
| applicant_id | BIGINT | NOT NULL，FK → app_user.id | 申请人（匿名化后置空，故实际为可空，见设计细节 6） |
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
| decided_at | TIMESTAMPTZ | 可空 | 进入终态的时间 |
| anonymized_at | TIMESTAMPTZ | 可空 | 匿名化时间 |

索引与约束：
```sql
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
1. 状态机：`processing → accepted / rejected / withdrawn / invalid`，除 `processing` 外均为终态，终态后不可再变更。
2. “暂留”不是申请状态，而是发布者的私有标记（`publisher_mark='hold'`），此时 `status` 仍为 `processing`。
3. `invalid`（已失效）用于招聘被删除时，处理中与已接受的申请。已拒绝、已撤回的申请保持原状态。
4. 重投：撤回后重新投递会生成新记录；撤回的旧记录保留，这样就不会和部分唯一索引冲突。
5. 修改申请：仅 `processing` 状态可修改，新简历文件覆盖旧文件，不保留旧版本，不限次数；修改操作写入 AuditLog，同时置 `has_unseen_update = TRUE` 并通知发布者。
6. 数据保留：招聘关闭后申请记录保留 180 天，之后匿名化：删除简历文件，清空 `note`，`applicant_id` 置空，写入 `anonymized_at`，仅保留状态等统计值。
7. 简历访问权限：仅申请人本人、该招聘发布者可访问；`withdrawn` / `invalid` / 已匿名化的申请不返回文件。管理员在治理场景外不可见具体申请内容与简历。文件下载必须经过带权限校验的接口，不得暴露直链，也不得提供通过遍历用户标识获取他人简历的入口。
8. 发布者不能申请自己的招聘、只有 `open` 状态的招聘可投递，这两条涉及跨表比较，在 service 层事务内校验。
9. 接受申请时，在同一事务内：锁招聘行 → 校验 `accepted_count < max_headcount` → 更新申请状态 → `accepted_count + 1` → 若满员则置 `full` 并批量拒绝其余处理中申请。

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
2. 招聘被删除后，关联它的通知仍要保留，因此 `recruitment_id` 采用软删除，不级联删除。

### 1.6 EmailLog 邮件发送日志
| 字段名称 | 数据类型 | 约束 | 说明 |
|---------|---------|------|-----|
| id | BIGINT | PRIMARY KEY 自增 | |
| notification_id | BIGINT | NOT NULL，FK → notification.id | 对应的站内通知 |
| to_email | VARCHAR(254) | NOT NULL | 发送时的收件地址 |
| status | VARCHAR(16) | NOT NULL，默认 'pending'，CHECK (status IN ('pending','sent','failed')) | 发送状态 |
| attempts | INT | NOT NULL，默认 0，`0 <= attempts <= 3` | 已尝试次数，重试三次后标记 failed |
| last_error | TEXT | 可空 | 最近一次失败原因 |
| created_at | TIMESTAMPTZ | NOT NULL | |
| updated_at | TIMESTAMPTZ | NOT NULL | |

#### 设计细节
1. 仅在 `User.email_notify_enabled = TRUE` 时才创建记录。
2. 邮件正文只包含状态变更类型、关联信息名称、当前状态与站内链接。
3. 连续失败需要触发告警（运维需求）。

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
| actor_id | BIGINT | NOT NULL，FK → app_user.id | 操作者 |
| actor_role | VARCHAR(32) | NOT NULL | 操作时的基础身份（student / teacher） |
| actor_is_admin | BOOLEAN | NOT NULL | 操作时是否以管理员权限执行 |
| action | VARCHAR(32) | NOT NULL | 动作，如 recruitment_delete / admin_delete / resume_view / application_update / permission_denied |
| target_type | VARCHAR(32) | NOT NULL | 对象类型，如 recruitment / application |
| target_id | BIGINT | NOT NULL | 对象 id |
| reason | TEXT | 可空 | 原因（管理员删除时必填，在应用层校验） |
| created_at | TIMESTAMPTZ | NOT NULL | 操作时间 |

索引：`(target_type, target_id)`，`(actor_id, created_at DESC)`。

#### 设计细节
1. 必须记录的操作：管理员权限的行使、用户删除本人发布的招聘、发布者查看申请人简历、申请人修改申请、权限被拒绝的请求。
2. 日志保留不少于 1 年；只追加，不提供修改与删除接口。
3. 日志中不写入认证凭证、简历内容。

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
