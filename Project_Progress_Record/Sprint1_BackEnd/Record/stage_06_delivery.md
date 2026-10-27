# 阶段 6：回归与交付

日期：2026-10-27｜负责人：zf｜状态：已完成

## 核心交付

- 汇总阶段 4～5 的接口实现、测试命令、数据库回归结果和已知限制；分阶段记录分别见 `stage_04_processing.md` 和 `stage_05_notifications.md`，总索引为 `sprint1_delivery.md`。
- 更新唯一接口正文 `backend/design_file/api.md` 中阶段 4～5 的接口实现状态、路由挂载与交付边界；旧版 A 阶段说明文档 `backend/design_file/api_before.md` 链接到该正文。
- 为申请处理、通知权限及留存范围补充服务、HTTP、并发、文件、参数和 CSRF 测试。根据第一次测试输出修复 PostgreSQL 外连接行锁问题和相关测试数据/断言。
- Windows 环境无创建符号链接权限时，私有路径安全测试明确跳过符号链接子场景；其他路径穿越检查仍执行。
- 无新增运行时依赖或数据库迁移。完整交付不包含前端页面、正式认证、真实邮件发送、物理留存清理或周期任务平台。
- 补齐申请修改、撤回、接受/拒绝及实际改变暂留标记的 `application_update` 审计，并在 PostgreSQL 上重新运行阶段专项和完整测试集；以下结果为补丁后的实测结果。

## 验证结果

| 验证项 | 命令 / 结果 |
| --- | --- |
| Django 系统检查 | `python manage.py check`：通过，无问题 |
| Python 编译检查 | `python -m compileall -q apps\applications apps\notifications tests\applications tests\notifications`：通过 |
| 数据库无关策略与序列化回归 | `python manage.py test tests.applications.test_policies tests.applications.test_mutation_serializers tests.notifications.test_serializers --settings=config.settings.test --verbosity 2`：11 项通过 |
| 阶段 4～5 专项回归 | `python manage.py test tests.applications.test_services tests.applications.test_api tests.applications.test_mutation_serializers tests.notifications.test_api tests.notifications.test_serializers --settings=config.settings.test --verbosity 2`：28 项全部通过 |
| 完整 Sprint1 回归 | `python manage.py test tests --keepdb --noinput --settings=config.settings.test --verbosity 2`：201 项运行，200 项通过、1 项跳过；`tests.files.test_storage.StorageTest.test_names_and_path_escape` 因创建符号链接需要 Windows 开发者模式或提升权限而跳过 |
| 模型与迁移检查 | `python manage.py makemigrations --check --dry-run`：`No changes detected`；本次无模型迁移差异 |
| 差异空白检查 | `git diff --check`：通过 |
| HTTP / Session / CSRF | 申请变更接口与 Session/CSRF 专项测试通过；阶段 3 已有 HTTP 主流程复现记录。本阶段未另行执行浏览器端人工联调 |

## 完成边界

阶段 4～6 的后端接口、申请审计补丁后的专项与全量回归及交付文档均已完成。全量回归唯一跳过项及其 Windows 符号链接权限原因已记录。前端尚未实现，按规划以 HTTP 契约及可复制调用说明交付；阶段 3 的 `stage_03_applications.md` 已记录发布、投递、双方查询与简历下载的 HTTP 示例复现。本阶段未重复该手工端到端流程。

全量测试的唯一跳过项及其 Windows 符号链接权限原因已记录；若需验证该符号链接逃逸场景，可在启用 Windows 开发者模式或具有相应权限的环境运行 `tests.files.test_storage.StorageTest.test_names_and_path_escape`。
