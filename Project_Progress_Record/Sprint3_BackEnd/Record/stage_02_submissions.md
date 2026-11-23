# Sprint3 后端阶段 2 记录：公告投稿、审核与治理

日期：2026-11-23｜分工：zf｜执行依据：[Sprint3 后端开发计划](../Plan/sprint3_backend_plan.md) 阶段 2、[需求 3.1](../../../file/tasks/软件需求规格说明3.1.md) FR-02/FR-08/FR-09/FR-11｜状态：已完成

## 1. 范围

普通用户公告投稿与共享待审池、领取与审核（通过/驳回）、审核结果通知；收回全部公告编辑权限；所有公告删除通知发布人与投稿人并去重。涉及 `backend/apps/` 下 `announcements`、`notifications`、`audit` 模块。

## 2. 核心修改

### 2.1 投稿与审核（`announcements/models.py`、`services.py`、`serializers.py`、`views.py`、`urls.py`）

- 新增 `AnnouncementSubmission`（迁移 `announcements.0002`，含 `Announcement.submitted_by` 可空投稿人字段）：投稿内容与公告同口径（名称、正文、报名截止/活动时间、可选报名方式及链接）；状态 pending/approved/rejected 及领取、审核、驳回理由、生成公告关联，表级 CHECK 保证状态与审核字段一致。
- `POST /announcement-submissions`：任意已认证用户投稿；**上海自然日每人最多 5 条、同时待审最多 5 条（均含本次提交）**，按投稿人 advisory 锁串行判定，超限 409 `SUBMISSION_LIMIT_EXCEEDED`；驳回后再投按新投稿占用额度。提交后不能改稿、撤回（无编辑/撤回入口）。
- `GET /me/announcement-submissions`：本人全部投稿（状态、驳回理由、生成公告引用），他人不可见。
- `GET /admin/announcement-submissions`：共享待审池（仅 pending，`total` 为待审总数）；超 24 小时未处理优先并带 `overdue` 标记，组内按提交时间、编号升序。
- 审核动作 `POST /admin/announcement-submissions/{id}/{claim|release|approve|reject}`：领取存领取人与 15 分钟到期时间，可主动交回，到期可被其他管理员接手；通过/驳回在行锁内复核当前权限、领取人、期限及投稿状态，领取缺失/过期/非本人 409 `SUBMISSION_LOCKED`，重复处理 409 `SUBMISSION_ALREADY_PROCESSED`。通过按投稿原文生成公告（发布人记审核管理员、投稿人另记），驳回必填理由；审核结果、审计（`announcement_submission_approve`/`_reject`）与投稿人站内通知同事务提交。

### 2.2 编辑权限收回与删除通知（`services.py`、`views.py`、`admin.py`）

- 关闭 `PATCH /announcements/{id}`（405），移除更新服务与序列化器，后台编辑/新增入口一并收回；`permissions.can_edit` 恒为 `false`。
- **所有公告删除**（本人删除与治理删除）在同一事务内通知发布人与投稿人（两者相同只通知一次）：本人删除为 `announcement_removed`（含名称与处置结果），治理删除为 `announcement_admin_removed`（另含原因）；重复删除仅一次业务结果。

### 2.3 通知与审计（`notifications/`、`audit/`）

- 新增通知类型 `announcement_removed`、`announcement_submission_approved`（关联生成公告）、`announcement_submission_rejected`（含驳回理由，无目标关联）及对应文案模板。
- 接收人校验扩展：公告删除通知限发布人或投稿人，投稿通过通知限投稿人；驳回通知不带目标关联。旧通知兼容不变。
- 新增审计动作 `announcement_submission_approve`、`announcement_submission_reject`。

### 2.4 接口文档（`backend/design_file/api.md`）

第 7 章通知类型表、第 8 章整体重写：8.1 公告（编辑关闭、双删除入口与通知语义）、8.2 投稿与审核（对象、额度、领取与审核口径）、8.3 通用错误口径；新增三个投稿相关 409 错误码。

## 3. 测试结果

| 范围 | 结果 |
| --- | --- |
| 公告与通知测试（`tests/announcements`、`tests/notifications`，83 项） | 全部通过。阶段 2 覆盖：第 5 条可提交、第 6 条限额拒绝（每日/待审含本次）、待审额度随处理释放、待审池逾期优先与总数、两管理员领取竞争仅一人可处理、交回/到期后旧领取失效、通过生成公告（发布人/投稿人/审计/通知一次业务结果）、驳回理由必填与通知、无改稿撤回入口、普通用户 403、删除通知发布人与投稿人去重、编辑入口 405 与 `can_edit` 恒 false、并发领取/删除竞态、通知失败回滚删除 |
| 共享回归 `tests` 全量 | **349 项全部通过**（阶段 1 后 343 + 阶段 2 净增 6） |
| 系统检查、迁移差异检查 | 通过、无差异（`announcements.0002` 已应用于场景库） |

## 4. 完成情况与剩余事项

- 阶段 2 完成标准达成：提交与限额、领取竞争与交回/到期失效、每次审核/删除仅一次业务结果及对应审计与通知、普通用户仅见本人投稿与公开公告，均有用例。
- 设计决策：投稿不带关联招聘字段（按计划“沿用名称、正文、时间、可选报名方式及链接”）；审核动作要求先领取且在 15 分钟有效期内（无自动领取）；发布人即投稿人时删除只通知一次；驳回通知不设目标关联（投稿无公告实体）。
- 剩余事项：阶段 3 招聘、申请与简历权限收紧及中期交接。

## 5. 交接

- 扩展审核流程时保持“入口校验 + 行锁内最终复核”两层结构；领取判定用 `claimed_by` 与 `claimed_until` 双条件，勿只看其一。
- 通知新增类型须同步 `notifications/types.py` 的集合划分（`ANNOUNCEMENT_EVENTS` / `ANNOUNCEMENT_DELETION_EVENTS`）与接收人校验；删除类通知接收人集合为发布人∪投稿人。
- 投稿额度判定在事务内按投稿人 advisory 锁串行；`SUBMISSION_*` 三个错误码已入错误码表，勿改语义。
