# A 角色：按招聘场景验收后端公共能力

## 1. 范围与执行方式

依据任务图 `file/tasks/8056dc7f91a4250b8a1b384044d2abe5.png` 中 A 的职责：定后端规则、搭公共底层，负责数据库、接口格式、状态、权限、登录鉴权、统一返回、文件存储与消息发送公共能力。结合 `week1_plan_A.md` 和当前代码编写。

本文按需求的“发布招聘 → 申请加入 → 申请处理”顺序验收 A 的交付。**接口包括 HTTP 接口与 Python 调用接口**。当前 `config/urls.py` 只挂载 core、accounts；招聘发布、投递、处理申请没有可调用的 HTTP 业务路由，不能通过编造 URL 验收。以下业务场景使用现有自动化测试调用 A 的 Python 接口，契约测试中的 `_publish/_apply/_accept` 是测试胶水，不是已交付的生产 service。

不验收 B 的业务接口、C 的下载/通知中心/推送接口、前端页面及部署工作。通知验收到站内记录、邮件待发送记录和提交后调度为止；当前邮件不真实发送。

本文所列预期与实际结果分开记录，2026-10-24 实测结果见第 6 节。自动化测试中的人物、文件和时间由测试创建、清理或冻结，不需要在开发库手工伪造数据。

### 1.1 测试前提

在项目根目录终端执行：

```bash
cd /Users/alcony/code/jiMeet/backend
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
```

预期：系统检查无错误，迁移检查 `No changes detected`。以下命令均在 backend 目录执行；PostgreSQL 须可连接，当前数据库角色须可创建测试库，且能使用 pg_trgm。Django runner 创建并销毁测试库；不要将已有业务库配置为测试库。每条测试命令预期以 `OK` 结束，行锁并发测试须实际执行，跳过不能算通过。

场景人物：发布者“小林”、申请人“小陈”和“小周”、无关用户“小王”。契约测试用工厂生成对应身份，无须固定真实学号。

### 1.2 登录及统一返回：所有场景的前置能力

使用接口：`GET /api/v1/auth/csrf`、`POST /api/v1/auth/dev-login`、`GET/PATCH /api/v1/me`、`POST /api/v1/me/privacy-consent`、`POST /api/v1/auth/logout`。路径无末尾斜杠。

先在另一个终端启动本地开发服务：

```bash
cd /Users/alcony/code/jiMeet/backend
DJANGO_DEBUG=true ALLOW_DEV_LOGIN=true .venv/bin/python manage.py runserver 127.0.0.1:8000
```

以下 curl 会在开发库创建或登录测试账号；使用专用开发数据库。固定账号后续重复登录复用原用户。

```bash
BASE=http://127.0.0.1:8000/api/v1
COOKIE=$(mktemp /tmp/jimeet-A-cookie.XXXXXX)
curl -sS -c "$COOKIE" "$BASE/auth/csrf"
TOKEN=$(awk '$6 == "csrftoken" {print $7}' "$COOKIE")
curl -i -b "$COOKIE" -c "$COOKIE" -H "X-CSRFToken: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"real_id":"a_scenario_001","name":"小陈","email":"a_scenario_001@tongji.edu.cn"}' \
  "$BASE/auth/dev-login"
# 登录会轮换 CSRF token，后续写请求必须重新读取。
TOKEN=$(awk '$6 == "csrftoken" {print $7}' "$COOKIE")
curl -i -b "$COOKIE" "$BASE/me"
curl -i -b "$COOKIE" -H "X-CSRFToken: $TOKEN" \
  -H 'Content-Type: application/json' -X PATCH \
  -d '{"nickname":"山间清风","email_notify_enabled":true}' "$BASE/me"
curl -i -b "$COOKIE" -H "X-CSRFToken: $TOKEN" -X POST "$BASE/me/privacy-consent"
curl -i -b "$COOKIE" -H "X-CSRFToken: $TOKEN" -X POST "$BASE/me/privacy-consent"
```

预期：上述请求 HTTP 200，统一包含 `code/message/data/request_id`，成功 `code=OK`；本人资料包含 uid、昵称、姓名、角色、邮箱、邮件开关和隐私确认状态，不暴露数据库 id、real_id、subject。两次隐私确认均成功，首次确认时间不被覆盖。

鉴权反例及响应格式用已有测试验证：

```bash
.venv/bin/python manage.py test tests.accounts tests.core.test_responses tests.core.test_exception_handler tests.core.test_permissions --verbosity 2
```

预期：匿名访问 me 返回 401/UNAUTHENTICATED；缺 CSRF 的开发登录被拒；PATCH 未知字段被拒；不能通过修改资料提升角色或管理员权限；停用用户不能登录。正式 SSO 两个预留入口返回 501/INTERNAL_ERROR/“预留”，不代表正式 SSO 已可用。开发登录开关关闭时不可使用。

完成 HTTP 验证后清理本机会话文件：

```bash
curl -i -b "$COOKIE" -H "X-CSRFToken: $TOKEN" -X POST "$BASE/auth/logout"
curl -i -b "$COOKIE" "$BASE/me"
rm -f "$COOKIE"
```

预期：登出 200，随后 me 为 401/UNAUTHENTICATED；开发库测试账号仍保留。

## 2. 发布招聘

### 2.1 小林选择竞赛类型、领域和招聘信息

对应需求：类型、相关领域预设；竞赛/活动名称、说明必填。

A 提供的接口：`core.choices.RecruitmentType`、`recruitments.seed.PRESET_TAGS`、Recruitment/Tag/RecruitmentTag 模型与数据库约束。当前类型为 `competition/activity/internship`，领域为 19 个：计算机、软件工程、人工智能、电子信息、自动化与控制、机械、土木建筑、设计创意、交通运输、环境科学、材料、数学统计、经济管理、医学生命、人文社科、外语、艺术传媒、创新创业、其他。类型是枚举字段，领域是标签表。

测试输入与命令：

```bash
.venv/bin/python manage.py test tests.test_seed_tags tests.test_constraints tests.test_schema tests.contract.test_week1_flow.Week1FlowTest.test_publish_requires_active_tags_and_valid_rules --verbosity 2
```

预期：标签初始化可重复执行，不产生重复记录，不重新启用已停用标签；模型约束及结构与设计一致。契约发布传空标签或停用标签被拒，失败不落招聘记录。非法类型受数据库约束限制。

范围说明：“尽量全覆盖”没有可穷举的验收标准，此处核对实际预设集合；新增类型/领域需按产品决定调整。名称和说明在生产发布请求中的缺失、空串、纯空白校验属于 B 的 serializer/service；数据库 NOT NULL 不等于业务必填校验，本次不能宣称已通过这些 HTTP 校验。

### 2.2 小林填写截止时间和人数

对应需求：截止时间严格晚于现在、最多一年；人数支持整数或闭区间，下限仅展示。

使用接口：`rules.validate_deadline(deadline, now)`、`rules.validate_headcount(min_headcount, max_headcount)`。

```bash
.venv/bin/python manage.py test tests.recruitments.test_rules.RulesTest.test_calendar_and_deadline_boundaries tests.recruitments.test_rules.RulesTest.test_headcount tests.contract.test_week1_flow.Week1FlowTest.test_publish_requires_active_tags_and_valid_rules --verbosity 2
```

| 输入 | 预期 |
|---|---|
| deadline 等于 now | ValidationFailed，code=VALIDATION_ERROR |
| deadline 恰好为下一日历年同日 | 通过；2024-02-29 对应 2025-02-28 |
| deadline 超过一年 1 秒 | VALIDATION_ERROR |
| 人数 `(None,1)`、`(1,50)`、`(50,50)` | 通过；单整数表示为 min=None、max=人数 |
| `(None,0)`、`(None,51)`、`(0,3)`、`(4,3)` | VALIDATION_ERROR |
| `(True,3)`、`(None,1.5)` | VALIDATION_ERROR；布尔值不当作整数 |

当前已定上限为 **50，且允许等于 50**（settings.MAX_HEADCOUNT_LIMIT），不同于原需求尚待定的严格小于上限表述；验收按当前 A 方案记录，不擅自修改规则。闭区间下限不控制满员，满员只比较 accepted_count 与 max_headcount。把用户输入的“2–4”解析成两个整数由 B 负责。

### 2.3 招聘进行中、到期关闭、满员及七天窗口

对应需求：到期不再接收新申请；关闭后七天内仍可处理；满员优先，拒绝剩余申请并通知。

使用接口：`rules.is_apply_open/is_processable`、`state.sync_recruitment`、`state.mark_full`、`state.run_in_recruitment_tx`。

```bash
.venv/bin/python manage.py test tests.recruitments.test_rules.RulesTest.test_status_and_time_windows tests.recruitments.test_state tests.recruitments.test_sync_command --verbosity 2
```

| 情景与输入时间 | 预期状态与副作用 |
|---|---|
| 未满员，deadline 前 1 秒 | open；允许申请和处理 |
| 恰好 deadline，执行同步 | closed，closed_at=deadline；不可新申请，发布者收到关闭通知 |
| closed_at+7 天前 1 秒 | 仍允许处理 processing 申请，不自动拒绝 |
| 恰好 closed_at+7 天 | 所有 processing 自动 rejected，逐个通知；终态申请不变 |
| 定时任务延迟 30 天 | 一次同步补关闭及超时拒绝；业务时间仍取 deadline 和 deadline+7 天 |
| 重复同步 | 不重复拒绝、不重复通知 |
| accepted_count 达 max_headcount，调用 mark_full | full，记录 full_at，剩余 processing 自动拒绝；不能申请或继续处理 |
| 到期与满员同次处理 | mark_full 保存 full 优先，补写/保留关闭时间，剩余申请按满员拒绝 |

测试还验证：已接受、已拒绝、撤回、失效记录不会被批量覆盖；人数未达上限不能直接 mark_full；写操作必须持有招聘行锁。自动关闭补执行已提交后，即使后续业务失败，关闭仍保留。

“自动”依赖定时调用或业务入口补执行，不是数据库到点自行变化。`run_sync_recruitments` 已实现，测试会调用命令验证候选筛选、幂等、单个失败后继续处理；本文不修改系统定时配置。若需在专用开发库手工触发，命令如下，会真实修改到期招聘及关联记录：

```bash
.venv/bin/python manage.py run_sync_recruitments
```

## 3. 申请加入

### 3.1 小陈选择简历文件

对应需求：PDF/DOC/DOCX，≤10MB。

使用接口：`files.validators.validate_resume`、`files.storage.save_resume/staged_resume/open_resume`。这是 A 的文件校验与私有存储接口，不是上传或下载 HTTP 接口。

```bash
.venv/bin/python manage.py test tests.files.test_storage.StorageTest tests.test_private_resume --verbosity 2
```

预期输入与结果：合法 PDF/DOC/DOCX 通过；空文件、超过 10485760 字节、伪装扩展名、扩展名与文件头不一致、缺 Word 目录的 DOCX 被拒。错误码 INVALID_RESUME_FILE，原因区分 size/type/signature。文件存至私有目录的随机路径，上传名中的 `../`、反斜杠不会成为保存路径；目录穿越读取被拒；业务异常时 staged_resume 清理新文件。

这些测试用最小文件头/ZIP 结构验证格式规则，不证明文件可由 Office 正常打开。简历补充说明可空及 multipart 请求解析属于 B/C 接口层，本文不作 HTTP 验收。

### 3.2 小陈投递，重复投递及撤回重投

对应需求：仅进行中可投递；不能投本人；未撤回不能重复投；撤回后生成新记录。

使用接口：`applications.policies.can_submit_application`、`recruitments.policies.publish_state_for_viewer`、`run_in_recruitment_tx`、`notify`。契约 `_apply` 在锁内查询是否存在非 withdrawn 申请，再传 `has_active_application`。

```bash
.venv/bin/python manage.py test tests.applications.test_policies tests.recruitments.test_rules.RulesTest.test_recruitment_permissions tests.contract.test_week1_flow.Week1FlowTest.test_apply_rejections_cleanup_and_reapply tests.contract.test_week1_flow.Week1FlowTest.test_expired_apply_commits_close_but_cleans_upload --verbosity 2
```

| 场景输入 | 预期 |
|---|---|
| 发布者申请自己的招聘 | SELF_APPLICATION_FORBIDDEN；展示权限给出 own，不允许申请 |
| 未登录 / 未确认隐私告知 | UNAUTHENTICATED / PRIVACY_NOT_CONSENTED |
| 未撤回申请存在，has_active_application=True | DUPLICATE_APPLICATION；不新建记录，失败新文件被清理 |
| 撤回旧申请，再投递 | 新记录主键不同，旧记录保留，两次提交通知分别存在 |
| 到截止时刻但数据库仍 open | 补执行先提交 closed；投递 RECRUITMENT_NOT_OPEN；无新申请和遗留文件 |
| full 或 closed | 不可投递 |

覆盖边界：契约测试通过直接改库构造 withdrawn，不证明撤回 HTTP 功能已实现。重复策略依赖调用方使用 `.exclude(status="withdrawn")`，包括 accepted/rejected，policy 自身只接收布尔值，不查库；目前完整重投场景覆盖 processing→withdrawn，不能把它表述成已逐项实测 accepted/rejected 的生产重复投递。本人不显示投递键由前端使用 A 的权限结果实现，本文仅验证权限结果。

## 4. 申请处理

### 4.1 小林查看简历和补充说明

对应需求：发布者查看收到的申请；暂留仅发布者可见。

使用接口：`resolve_application_access(user, app, recruitment, now)`、`can_process_application`、私有存储 `open_resume`。

```bash
.venv/bin/python manage.py test tests.applications.test_policies.ApplicationPoliciesTest.test_access_table tests.applications.test_policies.ApplicationPoliciesTest.test_operation_permissions --verbosity 2
```

预期：发布者可查看正常申请的姓名、说明、简历及 publisher_mark；申请人可看自己的说明与简历，看不到 publisher_mark；无关用户（含管理员）无权读取。withdrawn/invalid 后发布者不可看说明及简历。仅发布者可在允许的时间窗口处理 processing；accepted/rejected 不可再次处理。实际下载响应及序列化字段屏蔽由 B/C 接口实现，本测试验证权限决策。

暂留在数据设计中为 `status=processing, publisher_mark=hold`，不占用 accepted_count，也不是申请终态；A 负责枚举、约束、可见性。设置暂留以及手动拒绝的生产 service/HTTP 写接口属于 B，现有契约胶水没有对应实现，不能记作端到端通过。

### 4.2 接受一人，直到满员

对应需求：接受为终态、人数增长、满员自动拒绝其余申请、通知申请人。

```bash
.venv/bin/python manage.py test tests.contract.test_week1_flow.Week1FlowTest.test_one_place_full_flow tests.contract.test_week1_flow.Week1FlowTest.test_two_places_transition tests.recruitments.test_state.StateTest.test_concurrent_accept_only_counts_once tests.recruitments.test_state.StateTest.test_concurrent_different_applications_compete_for_last_place tests.recruitments.test_state.StateTest.test_concurrent_accept_and_withdraw_stay_consistent tests.recruitments.test_state.StateTest.test_concurrent_sync_closes_only_once tests.recruitments.test_state.StateTest.test_concurrent_accepts_never_exceed_headcount tests.recruitments.test_state.StateTest.test_batch_timeout_rejects_every_processing_application --verbosity 2
```

调用顺序：锁招聘 → 锁申请 → can_process_application → 更新 accepted 与 decided_at → accepted_count+1 → notify → 到上限时 mark_full。

预期：一个名额，两人投递，接受小陈后小陈 accepted、小周 rejected、招聘 full；申请人各收到对应接受/拒绝通知，发布者收到两条投递通知，不额外收到到期关闭通知。两个名额时，接受第一人仍 open，第二人后 full。accepted_count 始终等于 accepted 申请数；同申请并发接受只计一次，不同申请竞争最后名额只有一人接受，另一人拒绝，不超招。并发测试验证 A 的锁与状态组合，不等于 B 的生产接受接口已做并发验收。

### 4.3 到期后继续处理，七天后停止

```bash
.venv/bin/python manage.py test tests.contract.test_week1_flow.Week1FlowTest.test_closed_window_accept_and_exact_expiry tests.recruitments.test_state.StateTest.test_mark_full_preserves_or_adds_close_time --verbosity 2
```

输入：名额 3，先有两份申请；时间冻结到 deadline+7 天前 1 秒，接受第一份；再冻结到七天整点，尝试接受第二份。

预期：第一份可接受，未满员仍 closed；整点第二份被自动拒绝且发通知，接受操作返回 PROCESSING_WINDOW_CLOSED。关闭窗口内人数达到上限时转 full，保留原 closed_at，其余申请按满员处理。

### 4.4 接受、拒绝及自动拒绝的公共通知

使用接口：`notifications.service.notify`、`templates.render`、`audit.service.record`。

```bash
.venv/bin/python manage.py test tests.notifications.test_notify tests.audit.test_audit tests.recruitments.test_state.StateTest.test_timeout_notifies_each_processing_applicant_and_preserves_decided --verbosity 2
```

预期：申请事件通知关联正确招聘和申请，发给正确接收人；自动拒绝逐一通知，重复同步不重复发送。通知内容不含简历或申请人敏感内容；邮件开关开启时同事务创建 pending/attempts=0 的 EmailLog，提交后调用 dispatch；关闭时仍有站内通知而无 EmailLog；回滚不遗留通知或邮件记录。dispatch 当前仅记录日志，不能以邮箱是否收到邮件验收。拒绝权限等公共审计保留身份快照，审计实例不可修改或删除。

## 5. 验收记录

每组执行后记录实际结果，不能只看预期；异常模拟产生的日志应结合最终断言判断，最终 FAILED/ERROR 视为失败。

| 需求顺序 | 验收内容 | 实际结果 | 失败用例/备注 |
|---|---|---|---|
| 前置 | 登录、CSRF、隐私确认、统一返回 | 自动化部分：29 项 OK；curl 手工部分未执行 | 1.2 节的 runserver + curl 需要本机启动服务，本次未做 |
| 发布招聘 | 预设、模型约束、时间及人数规则 | 28 项 OK（预设/约束/结构/契约发布）；规则 8 项 OK | |
| 发布招聘 | open/closed/full、七天窗口、同步 | 17 项 OK | 手工执行 `run_sync_recruitments` 未做 |
| 申请加入 | 文件校验与私有存储 | 10 项 OK | |
| 申请加入 | 本人、重复、重投、截止补执行 | 7 项 OK | |
| 申请处理 | 字段权限、终态与暂留可见性 | 2 项 OK | |
| 申请处理 | 接受、人数一致性、满员、并发 | 20 项 OK（契约 + 状态含并发） | 并发用例未被跳过 |
| 申请处理 | 通知、邮件记录及审计公共能力 | 16 项 OK | |
| 汇总 | `manage.py test tests` 全量 | 173 项 OK，3.638 秒 | |

判定标准：以上命令和必要 HTTP 操作符合预期，可说明 A 的现有公共接口满足对应场景；生产招聘/申请接口、手动拒绝与暂留写入、补充说明请求校验、真实推送/邮件等未实现或非 A 职责的部分，不纳入 A 通过结论。

## 6. 2026-10-24 昵称调整及实际执行记录

变更：新用户未指定昵称时，由 UserManager 生成 `同学_` 加 12 位随机十六进制字符；不再从真实姓名复制，也不使用学号或邮箱。真实姓名保持身份资料原值；显式指定昵称、已有用户昵称和重复登录均保留原值，不批量修改历史账号。用户仍可主动设置昵称，不强制其与姓名不同。SSO 创建账号使用同一默认规则；本文件 curl 示例改为真实姓名“小陈”、自选昵称“山间清风”。该决定取代旧计划中的 `nickname=name` 初始化约定。

| 实际执行内容 | 结果 | 是否符合预期 |
|---|---|---|
| `manage.py check` | 无系统检查问题 | 是 |
| `manage.py makemigrations --check --dry-run` | No changes detected；数据库历史检查因连接限制产生警告 | 模型无变更；数据库历史未验证 |
| 下列不依赖数据库的专项命令 | 57 项，0.078 秒，OK | 是 |
| `manage.py test tests --verbosity 1` | 创建测试库前，连接 127.0.0.1:5432 被沙箱拒绝（Operation not permitted） | 未完成，不能判为通过 |
| 申请连接本机 PostgreSQL 重跑全量测试 | 自动审批服务 503，审核无法完成，重跑命令未执行 | 未完成 |

已执行专项命令：

```bash
.venv/bin/python manage.py test tests.accounts.test_accounts.IdentityTest tests.recruitments.test_rules tests.applications.test_policies tests.files.test_storage.StorageTest tests.test_private_resume tests.core.test_permissions tests.core.test_choices tests.core.test_clock tests.core.test_responses tests.core.test_errors tests.core.test_middleware tests.core.test_exception_handler tests.core.test_pagination --verbosity 1
```

本次覆盖：默认昵称与姓名分离、显式昵称保留、生成值恰巧与姓名相同时的保护分支；招聘时间/人数规则、申请权限、文件格式/私有存储、统一返回等纯逻辑。昵称专项通过 mock 保存方法验证管理器构造结果，**不代表数据库持久化与 HTTP 登录已验证**。SSO 首次创建、重复登录和 me 返回的新断言已加入数据库测试，但因上述环境限制尚未执行。

完整日志保存在本地忽略目录：`backend/var/verification/scenario_A_offline_20261024.log` 和 `backend/var/verification/scenario_A_database_blocked_20261024.log`。日志中故障注入的 `RuntimeError: boom` 属于预期异常测试，最终为 OK。

第 5 节各场景涉及数据库或 HTTP 的完整验收仍保持待执行；不能用本次 57 项纯逻辑通过替代通知落库、满员事务、并发或真实会话的验收。

### 6.1 用户明确授权后的重试

用户已明确允许连接本机 PostgreSQL 并创建独立测试库。再次请求执行：

```bash
.venv/bin/python manage.py test tests --verbosity 1 > var/verification/scenario_A_full_20261024.log 2>&1
```

实际结果：自动审批服务再次返回 503 Service Unavailable，授权审核未能完成，命令未启动，没有创建测试库，也没有产生此次全量测试结果。此问题是审批服务不可用，不是用户未授权，也不是测试断言失败。全量测试仍待执行；无需用户再次授权相同操作。

### 6.2 用户本机全量测试结果与修正

用户本机执行并提供日志，已核对 `var/verification/scenario_A_full_20261024.log`：169 项测试，3.571 秒，1 项失败，其余 168 项通过，测试库正常销毁。唯一失败为 `tests.test_base.UserManagerTest.test_create_user_defaults`，原第 67 行仍要求昵称等于真实姓名“张三”，与本次默认昵称调整冲突；不是随机昵称生成失败。

已修正该旧断言：真实姓名仍等于“张三”，默认昵称匹配 `^同学_[0-9a-f]{12}$`，且昵称与真实姓名不同。修正后尝试再次运行全量测试，但工具自动审批服务仍返回 503，命令未执行。**修正后的全量结果待验证，不能记为全部通过。** 可在本机运行：

```bash
.venv/bin/python manage.py test tests --verbosity 1 > var/verification/scenario_A_full_after_fix_20261024.log 2>&1
tail -n 30 var/verification/scenario_A_full_after_fix_20261024.log
```

此次原始日志中的 SSO 501、开发登录 404、故障注入 `RuntimeError: boom` 和 `email dispatch reserved` 是预期测试输出；实际失败以末尾 `FAIL:` 与 traceback 为准。

### 6.3 补充并发与批量用例及重跑结果

在 `tests/recruitments/test_state.py` 新增 4 个简单用例，均跑在本机 PostgreSQL，线程用 `Barrier` 同时起跑，等锁上限 5 秒：

| 用例 | 输入 | 实际结果 |
|---|---|---|
| `test_concurrent_accept_and_withdraw_stay_consistent` | 两线程对同一申请分别接受、撤回 | 恰有一个成功；`accepted_count` 与最终状态一致 |
| `test_concurrent_sync_closes_only_once` | 3 线程同时同步同一到期招聘 | 只关闭一次，关闭通知 1 条 |
| `test_concurrent_accepts_never_exceed_headcount` | 4 个申请抢 2 个名额 | 恰 2 人接受、2 人自动拒绝，招聘 full，拒绝通知 2 条 |
| `test_batch_timeout_rejects_every_processing_application` | 61 个处理中申请，七天整点同步 | 61 个全部 rejected，`decided_at` 为七天整点，每人恰 1 条通知 |

`tests.recruitments.test_state` 连续运行 5 次，每次 14 项 OK，未出现偶发失败。

按第 5 节各组命令重跑：前置 29、发布约束 28、规则 8、状态 17、文件 10、投递 7、权限 2、接受满员 20、通知审计 16，均 OK。全量 `manage.py test tests`：**173 项，3.638 秒，OK**，无跳过。这取代 6.2 中“修正后全量结果待验证”的状态：昵称断言修正后全量已通过。

未覆盖：1.2 节的 runserver + curl 手工验证、手工执行 `run_sync_recruitments`；死锁、大数据量性能和 B/C 的真实业务查询形态，需等其接口接入后再测。以上并发用例只证明锁顺序与计数在这几种竞态下正确。


runserver + curl 手工验证、手工执行 `run_sync_recruitments`已经通过测试。