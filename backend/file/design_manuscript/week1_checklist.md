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
