# Sprint3 后端中期交接（zf → czh）

日期：2026-11-23｜分工：zf 完成阶段 1～3，czh 从本交接提交接续阶段 4～6｜执行依据：[Sprint3 后端开发计划](../Plan/sprint3_backend_plan.md)

## 1. 交付提交与迁移顺序

| 提交 | 内容 |
| --- | --- |
| `8735689` | 阶段 1：验证码 5 分钟、双方式登录与注册字段补强 |
| `75104af` | 阶段 2：公告投稿审核、编辑权限收回与删除通知去重 |
| `561a2b9` | 阶段 3：简历下载权限收紧并统一文件访问口径 |

分支 `backend-sprint3`。增量迁移（按序应用，远端场景库已应用）：

1. `accounts.0004`：`registration_verification` 增加 `purpose` 列（registration/login 用途隔离）与联合唯一约束；
2. `announcements.0002`：新增 `announcement_submission` 表、`announcement.submitted_by` 可空投稿人字段。

无数据修复类迁移，历史数据默认兼容（purpose=registration、submitted_by 为空）。阶段 5 清理任务涉及的聚合/外键迁移由 czh 按计划另行编写。

## 2. 已交付接口与接口变化

**新增（阶段 1）：** `POST /auth/login/send-code`（登录验证码，与注册验证码共享 60 秒重发间隔与发送额度）；`POST /auth/login` 扩展为邮箱加密码或邮箱加验证码二选一（验证码一次性消费、绑定用途/邮箱/会话）；`POST /auth/register` 必填 `role` 与 `password_confirm`，重复注册提示“该邮箱已注册，请登录”；`POST /auth/register/verify-code` 响应增加 `account_exists`（仅验码成功后提示）。

**新增（阶段 2）：** `POST /announcement-submissions`（投稿，上海自然日 5 条/待审 5 条限额）、`GET /me/announcement-submissions`、`GET /admin/announcement-submissions`（待审池，逾期优先 + `overdue`）、`POST /admin/announcement-submissions/{id}/claim|release|approve|reject`（领取 15 分钟、通过生成公告、驳回必填理由）。

**关闭/收紧：** `PATCH /announcements/{id}` 关闭（405，`permissions.can_edit` 恒 false，后台编辑入口同收）；`GET /applications/{id}/resume` 及简历元数据收紧为发布者仅处理中/已接受可读（已拒绝/已撤回/已失效禁读）。

**错误码：** 新增 `SUBMISSION_LIMIT_EXCEEDED`、`SUBMISSION_LOCKED`、`SUBMISSION_ALREADY_PROCESSED`（均 409）。**通知类型：** 新增 `announcement_removed`、`announcement_submission_approved`、`announcement_submission_rejected`；所有公告删除通知发布人与投稿人（相同只通知一次）。完整契约见 [api.md](../../../backend/design_file/api.md)（第 4、7、8 章已随实现更新）。

## 3. 已验证场景（共享回归 350/350 通过）

- 注册登录：新用户建号、密码/验证码两种登录、验码前后重复注册提示、两次密码不一致、验证码过期/错码 5 次作废/会话与用途串用/一次性消费、发码统一受理、未注册与停用账号的验证码登录拒绝、真实 HTTP 契约链路。
- 公告投稿审核：第 5 条可提交与第 6 条限额拒绝、待审额度随处理释放、待审池逾期优先与总数、两管理员领取竞争仅一人可处理、交回/到期后旧领取失效、通过生成公告（发布人/投稿人/审计/通知同事务）、驳回理由与通知、无改稿撤回入口、普通用户 403。
- 公告治理：编辑入口 405、删除双入口、删除通知发布人与投稿人去重、重复删除无重复副作用、并发删除/领取竞态、通知失败回滚。
- 招聘申请（既有回归）：200/201 人数边界、最后名额竞争、七天到期自动拒绝、删除失效与人数归零、满员优先、撤回重投、未读标记、治理删除含原因通知发布者。
- 简历文件：五种申请状态下申请人/发布者/管理员的访问矩阵（发布者仅 processing/accepted 可预览与下载）、删除后全量禁读、私有存储与 10 MiB 边界、179/180/181 天长期记录可见。

## 4. 聊天入口可用标识（阶段 4 联调）

- **公开用户编号**：`User.uid`（32 位十六进制），出现在 PublicUser（`uid`/`nickname`/`role`）、公告 `author`、投稿 `submitter`、申请 `applicant` 等输出中；`GET /users/{uid}`（阶段 4 拟定）以此为路径标识，服务端须按 uid 反查并校验来源关系。
- **招聘标识**：`Recruitment.id`（正整数），见招聘列表/详情与 `RecruitmentReference.id`。
- **申请标识**：`Application.id`（正整数），见申请摘要/详情；联系申请人的来源校验可用“申请 → 招聘 → 发布者”关系链。
- 不输出 `real_id`、邮箱等内部标识；聊天建立会话的来源校验（公开招聘发布者 / 本人招聘的申请人）以业务关系为准，禁止仅凭任意 uid 新建会话。

## 5. 剩余事项（阶段 4～6）与接续注意事项

- 阶段 4 对方主页与聊天：按计划复用 `chat` 既有会话/消息表；限流（50 条/分、超限停 1 分钟）与六个月清理按计划实现。
- 阶段 5 清理与注销：`application_status_history` 已在（Sprint2 迁移 `applications.0002`）；180 天清理聚合、注销匿名化按计划执行；注意 `registration_verification` 的 purpose 列与注销失效的交互。
- 阶段 6 运行支持：容器/HTTPS/调度/备份/告警说明，按实际路由核对 api.md 与数据库设计、需求验收用例。
- 接续约定：写操作沿用“入口校验 + 行锁内最终复核”；新通知类型须同步 `notifications/types.py` 集合划分与接收人校验；私有文件读取一律经 `resolve_application_access`/`download_resume`，勿绕过；共享回归命令 `python manage.py test tests --keepdb --noinput --settings=config.settings.test`。
