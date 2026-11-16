# 公告模块设计说明

公告面向已登录用户展示竞赛与活动信息，独立于招聘及申请。对外字段、请求示例与错误码以 [api.md](../api.md) 第 8 章为准；表结构见 [database.md](database.md) 第 1.9 节。

## 1. 模型与查询

- `Announcement` 保存作者、标题、纯文本正文、时间类型与时间值，以及可选的报名链接和招聘关联；作者和招聘外键采用 PROTECT。
- `time_kind` 为 `deadline` 或 `event`；`event_at` 为带时区时间，不限制必须晚于当前时刻。报名说明可放入正文，链接仅接受 HTTP/HTTPS 绝对地址。
- 列表仅返回未删除公告，按 `created_at DESC, id DESC` 稳定分页；预加载作者和关联招聘。保留 `is_pinned` 数据字段，HTTP 不提供置顶写入，也不按其排序。
- 关联招聘被关闭、满员或软删除不删除公告。`recruitment_available` 仅表示该招聘存在且未删除，不表示其仍可投递申请。

## 2. 权限与事务

| 操作 | 权限与行为 |
| --- | --- |
| 列表、详情 | 已登录用户；已删除或不存在的公告返回 404。 |
| 发布 | 当前业务管理员；写入审计，不广播通知。 |
| 编辑 | 当前业务管理员且为作者；其他管理员不能编辑。 |
| 本人删除 | 当前业务管理员且为作者；软删除并写入审计，不产生治理通知。 |
| 治理删除 | 当前业务管理员；原因必填，软删除、审计和作者通知同事务提交。 |

写服务锁定公告后重新校验删除状态、当前管理员权限与作者身份；撤销管理员权限后，既有会话也不能继续管理旧公告。重复删除返回 404，不恢复对象或重复创建通知。公告作者失去管理员权限后仍可读取本人收到的治理通知。

## 3. 模块职责

| 模块 | 职责 |
| --- | --- |
| `backend/apps/announcements/models.py`、`migrations/` | 模型、枚举约束、索引及迁移。 |
| `backend/apps/announcements/selectors.py` | 未删除公告查询、稳定排序与关联预加载。 |
| `backend/apps/announcements/serializers.py` | 严格输入校验、公开字段及关联招聘可用性输出。 |
| `backend/apps/announcements/services.py` | 锁内权限与状态复核、写入、审计和治理通知。 |
| `backend/apps/announcements/views.py`、`urls.py` | HTTP 入口、会话与 CSRF 校验、分页及统一响应。 |
| `backend/apps/notifications/` | 公告通知关联与读取，校验作者身份并提供目标删除提示。 |

公告治理通知仅关联公告，与招聘/申请关联互斥；包含公告名称、处置结果及原因，不恢复已删除公告的详情访问，不创建邮件任务。

共享回归位于 `backend/tests/announcements/`、`backend/tests/notifications/`；交付与验收结论见 `Project_Progress_Record/Sprint2_BackEnd/Record/`。
