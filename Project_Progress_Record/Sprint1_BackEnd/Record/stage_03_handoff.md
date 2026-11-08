# Sprint1 后端中期交接手册

日期：2026-10-26｜阶段 1～3：czh｜阶段 4～6：zf

## 1. 接手基线

本次交付可发布、浏览、投递、查询及受控下载的后端。功能基线提交：`cba7558655eb392d1e55822ec5344e681bec4284`；本手册在该功能提交之后补充，不改变业务实现。已核验的规划 `Project_Progress_Record/Sprint1_BackEnd/Plan/sprint1_backend_plan.md` 保持不变。接口字段、权限及错误码唯一正文为 `backend/design_file/api.md`。

| 项目 | 值 |
| --- | --- |
| 同济 GitLab 分支 | [feat/sprint1-backend-recruitment-czh](https://git.tongji.edu.cn/tokendance/jimeet/-/tree/feat%2Fsprint1-backend-recruitment-czh) |
| 版本状态 | 工作分支交付，尚未提交PR或合并 main |
| 数据库 / 依赖变化 | 无新增模型、迁移或运行时依赖，沿用原有迁移 |
| 配置修正 | `PRIVATE_FILE_ROOT` 未设置或为空时均使用 `backend/var/private`；该目录不提供静态 URL |

## 2. 已交付与待完成

全部路径前缀为 `/api/v1`，无末尾斜杠。

| 状态 | 接口 / 能力 |
| --- | --- |
| 已实现：身份与基础 | `GET /healthz`、`GET /auth/csrf`、`POST /auth/dev-login`、`POST /auth/logout`、`GET/PATCH /me`、`POST /me/privacy-consent` |
| 已实现：招募 | `GET /tags`、`GET/POST /recruitments`、`GET/PATCH/DELETE /recruitments/{id}`、`POST /recruitments/{id}/close`、`GET /me/recruitments` |
| 已实现：申请入口 | `POST/GET /recruitments/{id}/applications`、`GET /me/applications`、`GET /applications/{id}`、`GET /applications/{id}/resume` |
| 阶段 4 待实现 | `PATCH /applications/{id}`；`POST /applications/{id}/{action}`，action 为 `withdraw/accept/reject/hold/unhold/read`，共 7 个方法/路径 |
| 阶段 5 待实现 | `GET /notifications`、`GET /notifications/unread-count`、`POST /notifications/{id}/read`、`POST /notifications/read-all` |
| 本轮保留占位 | SSO 两个 GET 接口返回 501；真实邮件发送、留存清理、孤立文件和审计清理命令仍为 reserved |

共 20 个已实现、11 个待实现方法/路径及 2 个 SSO 占位。当前 `PATCH /applications/{id}` 返回 405，其余未注册的后续路径返回 404。业务权限字段表达当前身份和状态的操作条件，不代表阶段 4 方法已上线。前端可开始招募、申请提交、历史与详情、简历下载的开发；处理按钮须等待相应接口交付。

## 3. 代码入口与关键实现约定

| 位置（相对项目根目录） | 职责与接续要点 |
| --- | --- |
| `backend/apps/core/views.py`、`serializers.py` | `PrivateAPIView`、`validate_data` 统一严格输入和私有缓存；默认保留 Session/CSRF。申请上传仅接收 multipart，新增 JSON 动作应使用相应解析器。 |
| `backend/apps/applications/services.py` | `submit_application`：身份/隐私预检 → 事务外暂存 → 招募状态补执行 → 招募锁内复核窗口与重复投递 → 原子创建申请和发布者通知。 |
| `backend/apps/applications/selectors.py`、`serializers.py` | 归属与留存过滤、有效状态投影、字段白名单；列表在分页前过滤，关联对象批量加载。序列化器只接收已鉴权、已投影的快照。 |
| `backend/apps/applications/policies.py` | 对象访问、投递、修改/撤回、处理规则。管理员无额外申请或简历读取权限。 |
| `backend/apps/files/services.py`、`views.py` | `download_resume` 在招募锁 → 申请锁下复核权限、打开文件并记录发布者读取审计，提交后传输；失败关闭句柄。 |
| `backend/apps/files/storage.py`、`validators.py` | 校验 PDF/DOC/DOCX、10 MiB 上限与文件特征，生成随机私有路径；`staged_resume` 在业务失败时清理新文件。 |
| `backend/apps/recruitments/services.py`、`state.py`、`rules.py` | 招募变更、`run_in_recruitment_tx`、`mark_full`、截止与七天处理规则，供阶段 4 接续使用。 |
| `backend/apps/notifications/service.py`、`types.py`、`templates.py` | 通知与业务同事务；邮件日志已生成但真实发送未实现。提交后派发采用稳健回调，异常不能误触发文件回滚清理。 |
| `backend/apps/audit/service.py`、`core/exception_handler.py` | 业务审计和权限拒绝审计；原因不得包含简历内容、文件名、补充说明或凭据。 |
| `backend/config/urls.py` | 集中挂载业务路由；申请变更方法在对应应用接续。 |

关键约束：

1. 写既有招募/申请时不得在 `run_in_recruitment_tx` 外再套大事务；到期补执行独立提交，业务失败只回滚后续业务事务。锁顺序固定为招募 → 申请，同招募批量申请按主键排序，不额外锁关联用户行。
2. 接受申请后人数达到上限时，直接用 `mark_full` 同次保存人数与 full 状态，不先单独保存满员人数；其余 processing 由既有工具自动拒绝。数据库约束不能替代锁内业务复核。
3. 修改简历时先暂存新文件，业务失败清理新文件；提交成功后才清理旧文件。数据库提交后的通知派发或旧文件删除失败，不应被当作数据库已回滚，也不能删除新文件。
4. 招募软删除使 processing/accepted 失效，保留首次决定时间与历史人数；withdrawn/invalid 双方均不能下载，发布者也不能读取说明及私有标记。已拒绝或招募已关闭本身不禁止下载。
5. 当前 GET 使用有效时间状态，不保存状态、不清除未读修改。到关闭后七天边界显示 rejected；180 天留存从关闭、满员、删除的最早时间计算，过期即隐藏明细和文件，不能依赖物理清理任务。
6. 招募修改/删除只通知 processing/accepted 的申请人，已撤回和已拒绝者不通知；管理员删除另通知发布者。提交申请仅通知发布者，通知不携带申请正文或简历内容。
7. 阶段 4 的 `POST /applications/{id}/read` 使用详情的 `seen_updated_at`；锁内版本一致才清除标记，仅确认不刷新内容版本。不得改成 GET 顺带清除，也不得清掉读取后发生的新修改。

## 4. 运行与回归方式

环境基线为 Python 3.12+、PostgreSQL 15+，数据库使用 `pg_trgm`；依赖以 `backend/requirements/base.txt` 为准，配置项见 `backend/.env.example`。后端读取进程环境变量，不自动加载 `.env`。

| 方式 | 入口与说明 |
| --- | --- |
| 启动服务 | 配置项目环境后，在 `backend/` 通过 `manage.py` 的 `migrate`、`seed_tags`、`runserver` 命令完成迁移、标签初始化和启动。 |
| 共享回归 | 在专用测试数据库执行 `python manage.py test tests --keepdb --noinput --settings=config.settings.test`；该命令覆盖仓库既有 173 项测试，本阶段专项验证结果见 `Project_Progress_Record/Sprint1_BackEnd/Record/stage_03_applications.md`。 |
| 状态同步 | `python manage.py run_sync_recruitments` 用于到期关闭与七天自动拒绝；启动开发服务器不会自动周期执行该命令。 |

## 5. HTTP 复现方式

可使用浏览器、Postman 或其他 HTTP 客户端，依据 `backend/design_file/api.md` 调用已实现接口。会话与 CSRF 接入方式见第 3 节，招募接口见第 5 节，申请与简历接口见第 6 节。

参考流程：创建开发身份 → 发布招募 → 切换申请人身份并确认隐私告知 → 上传简历并提交申请 → 双方查询 → 发布者下载简历。字段可见性、错误码及状态边界以接口文档为准。

以上提供运行与复现入口，具体是否复现、采用何种工具及检查范围由后续负责人决定。

## 6. 后续阶段范围

| 阶段 | 接续工作 | 重点通过条件 |
| --- | --- | --- |
| 4：申请处理 | 在 applications 服务/视图/路由扩展接受、拒绝、暂留、取消暂留、修改、撤回、修改已阅确认；撤回重投继续复用现有 POST | 最后名额竞争不超员；重复/终态处理不重复通知；接受与撤回互斥；修改与已阅确认不丢未读；文件替换失败保留旧文件 |
| 5：关联与通知 | 在 notifications 补查询、序列化、视图、路由；联验招募与申请副作用、同步命令 | 列表/未读数/已读操作使用同一归属及留存范围；补执行幂等；关联目标仍受访问权限约束；不把邮件占位当作已发送 |
| 6：回归与前端交付 | 将必要场景整理为团队可重复执行的回归，维护接口状态和示例，提交 `Project_Progress_Record/Sprint1_BackEnd/Record/sprint1_delivery.md` | 真实 HTTP 全流程与权限、文件、并发、CSRF 均通过；前端可独立接入；区分已实现、占位和后续事项 |

后续阶段范围沿用已核验规划，接口契约由 `backend/design_file/api.md` 统一维护。完整登录/注册、正式认证、聊天、推荐、真实邮件发送、清理平台和正式部署继续保持本次范围边界。
