# Sprint2 后端阶段 3 记录与中期交接（zf → czh）

日期：2026-11-14｜分工：zf｜执行依据：[Sprint2 后端开发规划](../Plan/sprint2_backend_plan.md) 阶段 3、[阶段 1 记录](stage_01_baseline.md)、[阶段 2 记录](stage_02_auth.md)｜状态：已完成，进入中期交接

## 1. 交接基线

| 项 | 值 |
| --- | --- |
| 分支 | `backend_sprint2` |
| 交接提交 | `96ed947`（测试隔离修复）、`e1a2d69`（阶段 1 契约与附文）、`650a321`（阶段 2~3 功能） |
| 验证版本 | 全部测试与真实 HTTP 验证均在 `650a321` 对应代码与迁移状态上执行 |
| 协作约定 | czh 基于该提交接续阶段 4～6；zf 负责登录/公告缺陷的后续协作修复。写入前核对远端更新 |

## 2. 阶段 3 核心修改

### 2.1 公告 HTTP 层（`backend/apps/announcements/`）

- 新增 `serializers.py`、`views.py`、`urls.py`：`GET/POST /announcements`、`GET/PATCH/DELETE /announcements/{id}`、`DELETE /admin/announcements/{id}` 全部交付。
- 字段校验按冻结契约：title 1～100、content 1～5000、time_kind 枚举、event_at 带时区（不限未来时间）、link_url 仅 http/https 绝对地址 ≤500、recruitment_id 写入时须存在且未删除；`is_pinned` 与未知字段拒绝写入。
- 权限输出 `permissions` 区分 `can_edit`/`can_delete`（当前管理员且作者）与 `can_govern_delete`（当前管理员）；详情含 `recruitment_available` 表达关联招募可用性。
- 列表按 `created_at DESC, id DESC` 稳定分页，不按置顶排序（`selectors.list_announcements` 已同步）。

### 2.2 业务层锁内复核与治理删除（`services.py`）

- 发布、编辑、本人删除、治理删除均在行锁（`select_for_update`）内重新读取对象与操作者并复核状态、当前 `is_admin`、作者身份；捕获并发撤权。
- 本人删除无原因、无通知；治理删除原因必填（1～500 字），软删除、`announcement_delete` 审计与作者站内通知同事务提交。
- 重复删除统一 404，不重复写审计与通知；删除后更新按 404 处理，不复活对象。

### 2.3 通知扩展与邮件停止（`backend/apps/notifications/`）

- `Notification` 新增可空 `announcement` 外键（迁移 `0002_notification_announcement_and_more`），表级 CHECK 保证公告关联与招聘/申请关联互斥、申请必须同时关联招聘；旧通知兼容。
- 新增类型 `announcement_admin_removed` 与文案模板（含公告名称、处置结果、原因、公告引用）；`announcement_id` 进入通知响应。
- `notify()` 移除 `EmailLog(PENDING)` 创建与派发回调：业务事件只生成站内通知；`email_notify_enabled` 降级为兼容字段，`email_log` 表及历史数据保留，`run_send_emails` 等命令仍为 reserved。
- 旧测试已按新口径适配（不创建邮件记录、置顶不参与排序等）。

### 2.4 文档同步

- `backend/design_file/api.md`：公告与注册登录状态更新为已交付；可用方法/路径 38 个，另有 2 个 SSO 预留与 2 个待实现（阶段 4）。
- `backend/design_file/design_manuscript/database.md`：1.5、1.9 过时描述随实现修订（邮件排队停止、固定留存口径取消、删除双入口、不按置顶排序、`recruitment_available`），版本记录 v0.6。

## 3. 测试结果

| 范围 | 结果 |
| --- | --- |
| 新增 `tests/announcements/test_announcement_api.py`（12 项） | 全部通过：登录门槛、稳定排序且置顶无效、字段校验矩阵、过去时间公告、关联招募可用性、权限拒绝矩阵、部分更新、本人删除、治理删除含原因与通知、重复删除无重复副作用、更新/删除竞争不复活、撤权后全入口拒绝、集合 405、通知列表关联 |
| 新增/调整数据层与通知测试（`test_announcements.py`、`test_notify.py`） | 全部通过：锁内权限复核、治理删除同事务通知、重复删除 404、不创建邮件记录、公告通知关联互斥 |
| 共享回归 `tests` 全量 | **251 项全部通过**（218 基线 + 16 账号 + 17 公告/通知） |
| 系统检查、迁移差异检查 | 通过、无差异（含 notifications.0002 应用于场景库） |
| 真实 HTTP 验证 | 通过：管理员发布 201 → 普通用户列表/详情与权限输出 → 非管理员治理删除 403 → 管理员治理删除 200 并收到含原因与公告引用的通知 → 重复治理删除 404；`email_log` 新增 0 |

## 4. 已知限制与剩余事项（阶段 4～6，czh）

- **招聘与申请规则（阶段 4）**：`max_headcount` 上限 200 落地（当前实现仍限 50）；`DELETE /recruitments/{id}` 收敛为本人删除语义并新增 `DELETE /admin/recruitments/{id}` 治理删除；删除后人数归零、`application_status_history` 状态历史（database.md 4.3）与历史人数修复（4.4）；取消申请/简历查询的固定 180 天截断并落实本人下载保留简历、撤回/删除后发布者禁读。
- **通知与个人状态（阶段 5）**：按规划 2.4 通知矩阵统一核对接收人与去重（含招聘治理通知必须含原因，复用 `reason_label` 模板位）；移除通知生成/列表/未读数/已读中的 180 天截断；核对 `GET /me/applications` 五种状态与下载权限；确认业务事件零新增邮件任务。
- **联合验收（阶段 6）**：注册登录贯穿公告、招聘、申请、通知的完整链路；删除二次确认与两种管理入口的前端联调（前端就绪后）。
- **待确认事项**：《修订说明与待确认事项》P-01～P-10（人数上限落地、180 天移除、置顶能力、治理自通知口径等）。
- **已知限制**：GitHub 备份暂不可达（本机无授权密钥且 HTTPS 连接被重置），`backend_sprint2` 待补推；同济 GitLab 为协作来源。

## 5. 接续注意事项

- 契约唯一正文为 `backend/design_file/api.md`；错误码、字段与错误口径以阶段 1 冻结值为准，调整须先改契约与附文再实现。
- `auth_failure` 表为失败限流专用（摘要键），不用于业务查询；`notification.announcement_id` 与招聘/申请关联互斥，扩展会话注意既有 CHECK。
- 新增审计动作须登记 `apps/audit/actions.py` 的 `ALL`（管理命令类入 `SYSTEM_MANAGED`）；`admin_delete` 语义保持原因必填。
- 业务写操作沿用“入口校验 + 服务层锁内最终复核”两层结构；招聘/申请侧的锁顺序（招聘锁 → 申请锁）不变。
