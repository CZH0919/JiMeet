# A 第一周验收清单

## 第 1 天

- [x] 用户已在本机确认第一天验收正常。

## 第 2 天：模型、迁移与约束

以 `week1_plan_A.md` 第 3 章和 `database.md` 为准。设计实际定义了 10 张业务表，
因此按 10 张核对；Django 认证及权限关联表不计入业务表数量。

### 代码与独立检查

- [x] 补齐 10 张业务表的模型，外键使用 PROTECT 并显式命名 related_name。
- [x] `User.REQUIRED_FIELDS` 包含 name、email、nickname。
- [x] 生成各 app 初始迁移；招聘的 pg_trgm 扩展及两个 GIN 索引使用独立迁移。
- [x] 注册 User 和 Tag 的 Django Admin，不注册聊天模型。
- [x] 提供 19 个预设标签及幂等 seed_tags 命令，保留已有标签的停用状态。
- [x] 提供约束正反例测试、标签命令测试、Admin 测试和数据库结构测试。
- [x] `manage.py check` 通过。
- [x] `makemigrations --check --dry-run` 无模型变更；离线迁移图与模型状态一致。
- [x] 32 项不依赖数据库的测试通过，包含私有简历存储的 2 项测试。

### 本机 PostgreSQL 验收（已通过）

2026-10-24：根据用户回传的本机终端输出完成核对。开发库迁移全部成功，
预设标签首次新增 19 个、第二次新增 0 个；独立创建的 test_jimeet 数据库
从初始迁移构建成功，82 项测试全部通过（1.756 秒），无失败或跳过，测试库随后销毁。
开发库的 10 张业务表已逐表对照字段、类型、空值、默认值、约束及索引，符合第二天要求。
健康检查故障模拟和未处理异常模拟产生的 ERROR 日志属于预期测试输出。

- [x] 按 accounts → recruitments → applications → notifications → audit → chat 顺序迁移成功。
- [x] `seed_tags` 连续执行两次成功，第二次新增 0 个。
- [x] `tests.test_constraints`、`tests.test_seed_tags`、`tests.test_admin`、`tests.test_schema` 全部通过。
- [x] 全量 tests 通过；Recruitment / Application 已实现，7 项行锁及关联查询测试均已实际执行并通过。
- [x] 逐表核对下面 10 张表的字段、NOT NULL、默认值、约束和索引。

| 业务表 | 模型与迁移已准备 | PostgreSQL 实表已核对 |
|--------|------------------|----------------------|
| app_user | [x] | [x] |
| recruitment | [x] | [x] |
| tag | [x] | [x] |
| recruitment_tag | [x] | [x] |
| application | [x] | [x] |
| notification | [x] | [x] |
| email_log | [x] | [x] |
| audit_log | [x] | [x] |
| chat_conversation | [x] | [x] |
| chat_message | [x] | [x] |

### 本机执行命令

在终端粘贴整段命令。迁移按计划逐个 app 应用；随后补齐 Django 内置迁移。
命令失败即停止，不使用 `--fake`，不覆盖现有数据库。输出保存到忽略目录
`backend/var/verification/day2.log`，便于回传验收结果。

```bash
cd /Users/alcony/code/jiMeet/backend
mkdir -p var/verification
bash <<'BASH' 2>&1 | tee var/verification/day2.log
set -euo pipefail
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
for app in accounts recruitments applications notifications audit chat; do
    .venv/bin/python manage.py migrate "$app"
done
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_tags
.venv/bin/python manage.py seed_tags
.venv/bin/python manage.py test tests --verbosity 2
for table in app_user recruitment tag recruitment_tag application notification email_log audit_log chat_conversation chat_message; do
    PGPASSWORD=jimeet psql -X -v ON_ERROR_STOP=1 -P pager=off \
        -h 127.0.0.1 -U jimeet -d jimeet -c "\d+ $table"
done
BASH
```

若本机数据库连接使用了自定义环境变量，请保留原有 DB_* 配置，并将 psql 的
连接参数同步为同一数据库；上面的 psql 参数沿用计划中的本地默认值。

### 核对重点

- `recruitment` 有 5 条表级状态/时间约束、3 条人数范围约束和 3 条枚举约束。
  普通索引共 5 条，其中 publisher 索引无条件，其余 4 条带条件；另有两个 GIN 索引。
- `application_recruitment_status_idx` 沿用设计的完整名称，通过 PostgreSQLIndex
  使用 PostgreSQL 的名称长度上限；其余索引不受 Django 默认 30 字符限制影响。
- 简历字段按数据库设计命名为 resume_file、resume_name；测试工厂已同步。
  FileField 使用 PRIVATE_FILE_ROOT，不生成公开 URL。
- `Notification.type` 与 `AuditLog.action` 有意不加 CHECK；actor_role 是身份快照。
- 审计实例禁止更新和删除；新实例显式指定已有主键时也只能 INSERT，不能覆盖旧日志。
  按计划，实例保护不替代数据库权限管理，业务代码不得调用 QuerySet.update/delete 绕过。
- `tests.test_schema` 自动核对测试数据库中 10 张业务表的列、空值约束、默认值存在性、
  命名约束/索引及 pg_trgm/GIN；开发库已按用户回传的 `\d+` 输出逐表核对。

## 第 3 天：rules、policies、notify、audit

### 实现项（待本机验收）

- [x] 提供招聘纯规则函数：截止时间、人数、七天窗口、180 天留存起算及操作窗口。
- [x] 提供招聘权限与 PublishView，以及申请字段权限 ApplicationAccess 和操作权限。
- [x] 管理员不增加申请内容读取权限；撤回/失效申请不返回简历；到留存期限全部不可见。
- [x] 提供通知类型、固定模板及事务内 notify，邮件记录同事务创建，提交后调用预留 dispatch。
- [x] 申请事件及发给申请人的招聘更新/删除通知关联申请和招聘，并受留存期限限制。
- [x] 提供审计动作与 record，保存身份快照、截断原因，接通业务及 DRF 权限拒绝审计。
- [x] 添加关键边界与事务测试，沿用 Django runner 和现有测试工厂。
- [x] 用户执行第三天测试及全量回归通过。

### 本机执行命令与预期

```bash
cd /Users/alcony/code/jiMeet/backend
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test tests.recruitments.test_rules tests.applications.test_policies tests.notifications.test_notify tests.audit.test_audit --verbosity 2
.venv/bin/python manage.py test tests --verbosity 2
```

预期：系统检查无错误；迁移检查输出 No changes detected；第三天测试和全量测试
均以 OK 结束。此次没有修改模型，无需新增迁移。数据库测试要求本机 PostgreSQL
可连接，jimeet 角色可创建 test_jimeet，pg_trgm 扩展可用，沿用第二天环境。

核对重点：到截止时刻不可投递，关闭满七天不可处理，留存满 180 天不可读取；
通知回滚时邮件记录和提交回调也一并取消；邮件开关关闭时仍创建站内通知，
但不创建 EmailLog。dispatch 只记日志，EmailLog 保持 pending、attempts=0。
权限拒绝审计写入失败和未处理异常模拟产生的 ERROR 日志属于预期测试输出。

## 第 4 天：state + files

### 实现项（待本机验收）

- [x] 提供 SyncResult、sync_recruitment、reject_processing_applications、mark_full。
- [x] 提供 run_in_recruitment_tx，补执行先提交，业务回调失败仅回滚第二个事务。
- [x] core.tx 增加线程本地招聘锁记录、事务身份检查与上下文清理。
- [x] 到期关闭取 deadline，七天拒绝取 closed_at + 7 天，满员拒绝取 full_at。
- [x] 提供 PDF/DOC/DOCX 扩展名、声明及实际大小、文件头与 DOCX 目录校验。
- [x] 提供 StoredResume、随机排他创建、fsync、展示名清洗及私有路径校验。
- [x] 提供 staged_resume 异常清理、discard_resume 和分批 cleanup_orphans。
- [x] 提供状态、事务回滚、双线程行锁、文件校验与孤立文件清理的关键测试。
- [ ] 用户执行第四天专项测试与全量回归通过（本次未执行测试）。

### 调用约定

- 达到人数上限时，在持有招聘锁的对象上增加 accepted_count 后直接调用
  mark_full；由它把人数与 full 状态一起保存。不可先单独保存满员人数，
  否则会违反 recruitment_full_chk。业务回调中先重新读取申请状态再决定操作。
- sync_recruitment 和 run_in_recruitment_tx 禁止嵌入调用方外层 atomic。
  直接使用 lock_recruitment 的调用方可用 recruitment_lock_scope 管理锁记录。
- save_resume 在事务外调用，返回 path 为 PRIVATE_FILE_ROOT 下的相对路径。
  staged_resume 的 with 块必须覆盖数据库事务退出；成功后才清理旧文件。
- cleanup_orphans 不挂定时命令，referenced 回调分批接收相对路径并返回已被
  Application 引用的路径集合。只清理 mtime 严格早于 24 小时门槛的未引用文件。
- 本次不修改模型、迁移或数据库设计；mail.dispatch 仍为日志预留实现。

### 本机执行命令与预期

```bash
cd /Users/alcony/code/jiMeet/backend
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test tests.recruitments.test_state tests.files.test_storage tests.core.test_tx --verbosity 2
.venv/bin/python manage.py test tests --verbosity 2
```

预期：系统检查无错误，迁移检查输出 No changes detected，专项及全量测试均以
OK 结束。在 PostgreSQL 下双线程行锁测试应实际执行，不应跳过。测试沿用第二天
的测试库创建权限和 pg_trgm 环境。故障模拟中的 WARNING/ERROR 日志不代表失败，
以最终测试结果为准；文件测试使用临时目录，不改动现有简历文件。

### 第四天测试覆盖补充（待运行）

- [x] 关闭通知核对接收人为发布者，同时核对 recruitment_id 和 application_id。
- [x] 多个 processing 申请分别收到恰好一条拒绝通知；重复补执行不增加通知。
- [x] accepted / withdrawn / rejected / invalid 申请所有字段保持不变，不产生拒绝通知，接受人数不变。
- [x] 含 ../ 与反斜杠的上传名直接进入存储层，验证随机保存路径不含用户目录与文件名。
- [x] 增加不同申请竞争最后一个名额的并发测试，验证一人接受、一人拒绝、人数为 1、招聘满员及拒绝通知关联正确。
- [x] 用户运行补充测试及回归通过。

上述并发测试验证底层锁与 mark_full 的组合；完整业务 service 的接受/撤回冲突
仍需在对应 service 实现后做接口或 service 层契约测试。

## 第 5 天：accounts + 契约测试

### 实现项（待本机验收）

- [x] identity 提供临时角色判定（带 TODO）与允许域名的合法邮箱校验。
- [x] 定义 SSOIdentity、SSOProvider、DevSSOProvider、CasSSOProvider 预留方法。
- [x] login_with_sso 按 subject / real_id 查找、绑定或创建，拒绝身份冲突和停用账号。
- [x] update_profile 校验昵称与严格布尔开关；give_privacy_consent 条件更新首次时间。
- [x] 注册 SSOBackend，同时保留 Django ModelBackend 的 Admin 密码登录能力。
- [x] 提供 CSRF、dev-login、logout、GET/PATCH me、privacy-consent 与 SSO 501 预留接口。
- [x] 开发登录只在 DEBUG 与 ALLOW_DEV_LOGIN 同时开启时注册，匿名登录显式校验 CSRF。
- [x] 本人资料含 name / email，不暴露数据库 id、real_id 或 subject；更新拒绝未知字段。
- [x] 契约测试用 A 的 Python 接口与 ORM 覆盖计划 6.2 全部七类场景。
- [x] 契约测试额外验证活动标签、通知接收人及关联、新文件失败清理。
- [ ] 用户执行账号测试、契约测试与全量回归通过（本次未执行测试）。

### 调用与开发约定

- 所有账号接口位于 /api/v1/，无末尾斜杠。先 GET /auth/csrf，再用返回的
  csrf_token 作为 X-CSRFToken，携带同一客户端 cookie POST /auth/dev-login。
  登录会轮换 CSRF token，后续写请求使用新 csrftoken cookie 的值或重新获取 token。
- dev-login 接收 real_id、可选 name/email；默认姓名为编号，默认邮箱为
  <real_id>@tongji.edu.cn，稳定 subject 为 dev:<real_id>。仅作开发身份，不能用于生产。
- 正式 SSO 两个 GET 接口返回 501 / INTERNAL_ERROR / 预留；CAS 方法抛 reserved。
- 登录已存在用户不覆盖昵称、姓名、邮箱、角色、管理员权限、通知开关和隐私确认。
  相同 subject 对应不同编号或编号已经绑定其他 subject 时返回 AUTH_FAILED。
- 契约测试的 _publish / _apply / _accept 仅为 B 提供底层调用参考，不是生产业务 service。
  满员人数与 full 状态一起保存；七天整点优先返回 PROCESSING_WINDOW_CLOSED。
- 本次不修改模型、迁移、database.md，不提前实现第六天管理命令与交接文档。

### 本机执行命令与预期

```bash
cd /Users/alcony/code/jiMeet/backend
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test tests.accounts tests.contract --verbosity 2
.venv/bin/python manage.py test tests --verbosity 2
```

预期：系统检查无错误；迁移检查 No changes detected；专项与全量测试均以 OK
结束。账号测试使用真实 session 和强制 CSRF 检查；契约测试使用临时简历目录，
邮件仍只调度预留函数，不发送邮件。数据库要求沿用此前 PostgreSQL 测试环境。

### 第五天账号测试覆盖补充（待运行）

- [x] 验证密码认证落到 ModelBackend，错误密码被拒，真实 Admin 登录表单及后台会话可用。
- [x] 不重载已注册开发路由，关闭运行期开关后由视图返回 404，且不创建用户或登录会话。
- [x] 开发登录传入 name/email，核对数据库资料和登录响应 data 与 GET /me 一致。
- [x] 模拟首次建号的 IntegrityError，验证转换为 AUTH_FAILED/401 且不泄露数据库错误。
- [x] 明确当前匿名 POST /auth/logout 返回统一 UNAUTHENTICATED/401；保持现有行为。
- [ ] 用户运行补充账号测试及全量回归通过。

IntegrityError 补充用例为确定性故障注入，不代表真实并发首次登录测试；
现有邮箱唯一冲突用例另外验证 PostgreSQL 实际唯一约束错误的转换。
