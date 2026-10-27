# 阶段 5：关联流程与通知接口

日期：2026-10-27｜负责人：zf｜状态：已完成

## 核心修改

- 在 `backend/apps/notifications/` 增加通知查询、序列化、已读服务、视图与路由；由 `backend/config/urls.py` 集中挂载。
- 实现 `GET /notifications`、`GET /notifications/unread-count`、`POST /notifications/{id}/read` 和 `POST /notifications/read-all`。
- 列表与未读数按当前接收者、关联申请/招募权限及 180 天留存期限过滤；单条和全部已读操作复用同一可见范围。单条已读只锁定通知行，兼容 PostgreSQL 对外连接行锁的限制。
- 未知查询字段、重复查询参数、非法 `is_read` 值及不允许的请求体返回参数错误。重复标记已读保持幂等；用户不能查看或修改其他用户的通知。
- 通知保留现有类型和正文，不在读取时触发邮件发送；邮件真实发送仍未接入。
- 接口契约和实现状态更新在当前唯一接口正文 `backend/design_file/api.md` 第 7 节及接口清单中。

## 验证结果

| 验证项 | 结果 |
| --- | --- |
| 阶段专项回归 | `python manage.py test tests.applications.test_services tests.applications.test_api tests.notifications.test_api --settings=config.settings.test --verbosity 2` 中的通知接口专项通过 |
| 列表和计数 | 已读筛选、未读数、分页响应、失效关联通知过滤通过 |
| 归属及幂等 | 自有通知单条/全部已读、重复操作成功；他人通知不可见不可改 |
| 参数契约 | 非法、重复 `is_read` 查询参数和非空未声明请求体被拒绝 |
| PostgreSQL 行锁 | 已阅操作的行锁范围限于通知本身；关联对象存在外连接时可正确完成 |

## 完成边界

站内通知列表、未读数及已读操作均已交付。关联申请或招募到留存期后，通知不再展示或计入未读数；通知和邮件日志的物理清理、真实邮件发送及完整周期任务平台仍属范围外事项。
