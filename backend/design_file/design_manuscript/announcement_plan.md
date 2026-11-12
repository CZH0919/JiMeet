# 公告功能（FR-09）数据库与数据接口实现规划

> 状态：设计已按审核意见确认，database.md 1.9（v0.4）已同步；代码尚未编写。
> 范围：只含数据库表结构和基础的数据库读写接口，不含复杂业务逻辑，业务编排由后端协作者负责。

## 1 已确认的决定

| 事项 | 决定 |
|---|---|
| 新增字段 | `time_kind`、`event_at`（必填）、`link_url`（可空）；“报名方式”等写在 `content` |
| 发布权限 | `is_admin` 用户 |
| 编辑权限 | 仅发布者本人，其他管理员也不能编辑 |
| 删除权限 | 发布者本人或任一管理员；理由可选，写入 AuditLog.reason |
| 置顶 | 保留 `is_pinned`，只通过编辑接口（PATCH）修改，不设独立的置顶接口；发布者本来就是管理员，不另做限制；置顶变更与编辑合并，统一记 `announcement_update` 审计 |
| 查看权限 | 已登录用户；未登录不可查看 |
| 通知 | 发布公告不生成站内通知和邮件 |
| 排序 | `is_pinned DESC, created_at DESC, id DESC`；无置顶时即为发布时间倒序 |

## 2 表结构

以 database.md 1.9 为准，这里不重复字段表。要点：
- 表名 `announcement`，外键 `author_id`、`recruitment_id` 均 PROTECT。
- CHECK：`time_kind IN ('deadline','event')`。
- 索引：`announcement_list_idx`（`is_pinned DESC, created_at DESC`，条件 `deleted_at IS NULL`）；`announcement_recruitment_idx`（`recruitment_id`，条件非空）。
- `event_at` 是否晚于当前时间、`link_url` 格式由应用层校验。

## 3 将修改和新增的文件

新增 `backend/apps/announcements/`：

| 文件 | 内容 |
|---|---|
| `__init__.py`、`apps.py` | 应用注册 |
| `models.py` | Announcement 模型，含 CHECK 与索引 |
| `migrations/0001_initial.py` | 由 `makemigrations` 生成 |
| `selectors.py` | 只读查询 |
| `services.py` | 薄的写入函数，同一事务内写表并写审计 |
| `admin.py`（可选） | Django Admin 查看公告 |

修改已有文件：

| 文件 | 改动 |
|---|---|
| `backend/config/settings/base.py` | `INSTALLED_APPS` 增加 `apps.announcements` |
| `backend/apps/audit/actions.py` | 增加 3 个常量 `ANNOUNCEMENT_PUBLISH`、`ANNOUNCEMENT_UPDATE`、`ANNOUNCEMENT_DELETE`，并加入 `ALL`；`audit/service.py` 不用改 |
| `backend/tests/test_schema.py` | 增加公告表的约束和索引断言 |
| `backend/tests/announcements/`（新增） | 模型约束、selectors、services 的测试 |

不需要改：`Recruitment`、`Notification`、`EmailLog` 的模型和迁移，`core/permissions.py`（已有 `IsAdminFlag` 和 `IsAuthenticatedBiz`）。

## 4 数据层接口（Python 函数，供协作者的视图调用）

只读，位于 `selectors.py`：

| 函数 | 说明 |
|---|---|
| `list_announcements()` | 未删除的公告，按 `is_pinned DESC, created_at DESC, id DESC` 排序，`select_related` 作者和关联招募；分页由 `core.pagination.paginate` 完成 |
| `get_announcement(announcement_id)` | 返回未删除的公告；不存在或已删除时返回 None |

写入，位于 `services.py`，每个函数在一个事务内完成“写表 + 写审计”：

| 函数 | 审计动作 | 说明 |
|---|---|---|
| `create_announcement(*, author, title, content, time_kind, event_at, link_url=None, recruitment=None)` | `announcement_publish` | 创建公告 |
| `update_announcement(announcement, *, actor, **fields)` | `announcement_update` | 更新 title、content、time_kind、event_at、link_url、recruitment、is_pinned |
| `soft_delete_announcement(announcement, *, actor, reason=None)` | `announcement_delete` | 设置 `deleted_at`，理由可选 |

权限判断不放在这些函数里，由协作者在视图层判断：

| 操作 | 判断 |
|---|---|
| 发布 | `IsAdminFlag` |
| 编辑（含修改 `is_pinned`） | `announcement.author_id == request.user.pk` |
| 删除 | `author_id == request.user.pk` 或 `request.user.is_admin` |
| 查看 | `IsAuthenticatedBiz` |

## 5 建议的 REST 接口（契约，由协作者实现视图和序列化）

路径沿用现有风格：前缀 `/api/v1/`，不带末尾斜杠。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/announcements` | 已登录 | 公告列表，分页 |
| GET | `/announcements/<id>` | 已登录 | 公告详情，含 `recruitment_id` 及招募链接所需信息 |
| POST | `/announcements` | 管理员 | 发布公告 |
| PATCH | `/announcements/<id>` | 仅发布者 | 编辑公告，可含 `is_pinned` |
| DELETE | `/announcements/<id>` | 发布者或管理员 | 软删除，请求体可带可选 `reason` |

置顶、取消置顶通过 PATCH 的 `is_pinned` 完成，没有单独的接口。

## 6 与其他文档的一致性

- database.md：已更新 v0.4 版本记录、1.9、1.8 的审计示例与必记操作、第 2 节关系图。
- `backend/design_file/api.md`：尚未加入公告接口。它的接口概览表目前只列已实现（可用）的接口，协作者实现视图后再补，状态标为“可用”。
- implementation_plan*.md、week1_*.md 是历史阶段的计划，不修改。

## 7 下一步

审核通过后按这个顺序做：models 与迁移 → audit 动作常量 → selectors 与 services → 测试。视图、序列化和 api.md 的更新交给协作者。
