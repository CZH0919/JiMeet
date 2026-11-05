# 阶段 4：申请处理与并发一致性

日期：2026-10-27｜负责人：zf｜状态：已完成

## 核心修改

- 在 `backend/apps/applications/` 补齐申请 multipart 修改、撤回、接受、拒绝、暂留/取消暂留及修改已阅确认的服务、视图、序列化和路由。
- 既有申请写操作先补执行招募状态，再按招募锁 → 申请锁顺序复核身份、申请状态和处理窗口；重用 `run_in_recruitment_tx`、`mark_full`，不引入模型或迁移变更。
- 接受达到最后名额时，在同一事务更新接受人数与满员状态，并拒绝剩余处理中申请；重复终态处理返回冲突，不重复计数或通知。暂留仅为发布者私有标记，不改变申请终态，也不发接受/拒绝通知。
- 申请修改置 `has_unseen_update` 并通知发布者。已阅确认比较客户端传入的 `seen_updated_at`；版本不一致时保留新修改标记，确认操作本身不改变内容版本时间。
- 简历替换先在事务外暂存新文件；事务失败清除新文件，事务提交后才尝试删除旧文件。撤回后双方均失去简历读取权限；撤回后重投沿用原提交接口生成新记录。
- 申请修改、撤回、接受/拒绝及实际改变暂留标记的操作会在业务事务中写入 `application_update` 审计记录；幂等暂留/取消暂留不重复审计，审计不保存申请说明或简历内容。
- 接口字段、状态、权限及错误码已更新到当前唯一接口正文 `backend/design_file/api.md`。

## 验证结果

| 验证项 | 结果 |
| --- | --- |
| 阶段专项回归 | `python manage.py test tests.applications.test_services tests.applications.test_api tests.applications.test_mutation_serializers tests.notifications.test_api tests.notifications.test_serializers --settings=config.settings.test --verbosity 2`：28 项全部通过 |
| 申请状态及并发 | 最后名额并发接受、接受与撤回竞争、重复终态处理、满员时拒绝剩余申请均通过 |
| 修改确认与文件替换 | 新修改不被旧版本确认清除；替换成功后清理旧文件，通知失败回滚时保留旧文件并清理新文件 |
| HTTP 与 CSRF | 申请动作路由、修改、接受、已阅确认及 Session/CSRF 校验通过 |
| 配置和静态检查 | `manage.py check` 通过；相关 Python 编译检查通过；无新增迁移 |

## 完成边界

申请、简历、权限、通知和审计均复用现有模型及共享工具，无新增运行时依赖和数据库迁移。接受/拒绝通知为站内通知；真实邮件发送仍未接入。接口详情见 `backend/design_file/api.md` 第 6 节。
