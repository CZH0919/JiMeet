# Sprint2 前端适配与 UI 改版记录

日期：2026-11-16｜前端分支：`frontend_design`｜对接基线：`backend_sprint2` 的 `backend/design_file/api.md`（2026-11-14）
需求基线：`docs/软件需求规格说明2.0修订稿.md`

## 1. 本轮范围

在后端已交付的 Sprint2 能力上完成前端适配与 UI 改版：

| 需求 | 交付内容 | 主要页面 |
| --- | --- | --- |
| FR-01 身份与准入 | 同济邮箱 + 密码注册/登录、会话恢复、退出、401 自动清理登录态 | `LoginPage`、`useAuth` |
| FR-02 身份与权限 | 以详情 `permissions` 驱动按钮；管理员治理入口与基础身份入口分离 | `JobDetailPage`、`AppHeader`、`ProfilePage` |
| FR-03 浏览与筛选 | 类型 / 标签 / 状态 / 关键词筛选、分页、剩余时间 | `JobsPage`、`JobCard` |
| FR-04 简历上传 | PDF/DOC/DOCX、≤10 MiB、即时校验、随申请 multipart 提交 | `FileUploader`、`ApplyDialog` |
| FR-05 招聘管理 | 发布/编辑（上限 200 人、截止一年内）、手动关闭、本人删除、申请管理 | `JobFormPage`、`JobDetailPage`、`JobApplicationsPage` |
| FR-06 状态变更 | 已满员/已关闭的按钮与提示以后端状态与权限为准 | 同上 |
| FR-07 申请处理 | 确认 / 暂留 / 取消暂留 / 拒绝；修改申请前先取详情避免清空说明 | `JobApplicationsPage`、`ProfilePage` |
| FR-08 站内通知 | 页头小喇叭下拉面板、未读角标、单条已读、全部已读、目标已删除提示 | `NotificationBell` |
| FR-09 竞赛与活动公告 | 首页公告列表 + 分页、公告详情、发布/编辑、本人删除、治理下架 | `HomePage`、`AnnouncementDetailPage`、`AnnouncementFormPage` |
| FR-11 管理员治理 | 招聘治理 / 公告治理两个入口，原因必填（1–500 字） | `AdminPage` |

聊天（FR-10）后端未交付接口，保留本地演示仓储并在页面上明确标注，不作为本轮验收内容。

## 2. UI 改版（按样式稿）

1. **首页改为通知公告**：白底大卡片 + 公告行（文档图标、标题、时间类型与关联信息、右侧发布时间）+ 数字分页，与样式稿一致。
2. **删除「通知」导航项与通知分页页**：`NotificationsPage.tsx`、`NotificationDrawer.tsx` 已移除；`/notifications` 旧链接重定向到首页。
3. **小喇叭取代通知栏目**：`NotificationBell` 固定在用户头像左侧，点击后从**页面右侧展开 400px 通栏面板**（移动端全宽 + 遮罩），含未读角标、类型图标、相对时间、「全部已读」与关闭按钮；打开时不再遮挡页头操作。
4. **站点 logo**：由 `docs/logo.jpg` 裁剪生成 `public/logo.png`，用于页头「济遇」左侧与 favicon；页头改为不透明白底，避免贴纸白边在半透明页头下露出。
5. **导航收敛为**：首页 / 招聘 / 个人中心 / 消息。
6. **视觉规范**：主色 `#2f6bff`、页面浅蓝渐变背景、白色卡片 `18px` 圆角、柔和阴影、`PingFang SC` 字体；颜色以 RGB 通道定义，支持 Tailwind 透明度修饰符。
7. **文案收敛**：删除重复、口语化的小字说明（如「身份仅用于…」「上传简历后提交…」等），保留必要规则提示；登录/注册失败改为表单内错误条 + toast 双提示。
8. **响应式**：`390px` 宽度下页头 4 个导航项、公告列表、招聘卡片、详情页与右侧通知面板均已核对；移动端隐藏副标题、缩小 logo 与导航间距。
9. **学号登录**：登录/注册只填学号（工号），右侧固定 `@tongji.edu.cn` 后缀，前端拼成完整邮箱提交；兼容误粘贴完整邮箱。
10. **logo 去白底**：`public/logo.png` 生成透明底版本，页头与登录页不再出现白色方块。
11. **提示样式**：改为顶部居中的浮层提示（彩色图标 + 白底圆角卡片 + 上滑淡入），替代原先的左侧色条样式；短消息按内容自适应宽度。
12. **公告入口**：首页「发布公告」仅管理员可见；个人中心新增「管理员功能」区（发布公告 / 内容治理后台），避免找不到入口。

## 3. 代码结构整理

- 删除前端本地「竞赛通知」特性（`competition_notice`），公告统一走后端 `/announcements`。
- 删除混合仓储中的本地招聘分支，`data/index.ts` 只保留两类实现：后端 HTTP + 聊天演示。
- 新增 `domain/format.ts`（时间格式化）、`data/mock/chatRepository.ts`（聊天演示）、`components/layout/NotificationBell.tsx`。
- 移除未被引用的 `domain/applicationStatus.ts` 及旧 mock 文件（`mock/db.ts`、`mock/seed.ts`、`mock/repository.ts`）。
- 清理无引用导出（`AuthUnavailableError`、`MARK_ACTION_LABEL`、`ToneBadge`、`SuccessMark`、`getCsrfToken`、`isFull`/`deriveJobStatus`）。
- `backend/design_file/api.md`、`design_manuscript/announcement_plan.md`、`design_manuscript/database.md` 更新为 Sprint2 版本，作为前端唯一接口依据。
- 历史 Mock 阶段执行计划归档为 `docs/EXEC_PLAN_前端_v1.md`。

## 4. 接口对接清单

| 方法 | 路径 | 前端调用点 |
| --- | --- | --- |
| GET | `/auth/csrf` | `data/http/client.ts#fetchCsrf`（启动、登录、注册、登出后） |
| POST | `/auth/register`、`/auth/login`、`/auth/logout` | `data/http/repository.ts#auth` |
| GET/PATCH | `/me`、`POST /me/privacy-consent` | `useAuth`、`ApplyDialog`、个人中心 |
| GET | `/tags`、`/recruitments`、`/recruitments/{id}`、`/me/recruitments` | `JobsPage`、`JobDetailPage`、`ProfilePage` |
| POST/PATCH | `/recruitments`、`/recruitments/{id}`、`/close` | `JobFormPage`、`JobDetailPage` |
| DELETE | `/recruitments/{id}`、`/admin/recruitments/{id}` | 本人删除 / 治理删除（两个入口） |
| POST/GET | `/recruitments/{id}/applications`、`/me/applications`、`/applications/{id}` | 投递、申请管理、我的申请 |
| PATCH/POST | `/applications/{id}`、`/withdraw`、`/accept`、`/reject`、`/hold`、`/unhold`、`/read` | 修改、撤回、处理、已阅确认 |
| GET | `/applications/{id}/resume` | 简历下载（文件流） |
| GET/POST | `/announcements`、`/announcements/{id}`、`/admin/announcements/{id}` | 首页、详情、发布/编辑、治理下架 |
| GET/POST | `/notifications`、`/unread-count`、`/{id}/read`、`/read-all` | `NotificationBell` |

## 5. 验收记录

| 项 | 结果 |
| --- | --- |
| `npm run typecheck`（`tsc --noEmit`，strict + noUnusedLocals） | 通过，0 error |
| `npm run build`（`tsc && vite build`） | 通过，产物 `dist/`；CSS 28.6 kB，JS 299.5 kB（gzip 88 kB） |
| 页面走查（1440×1000） | 首页公告、右侧通知面板、招聘列表、招聘详情、公告详情、个人中心、治理后台、登录页均正常 |
| 移动宽度走查（390×844） | 首页、右侧通知面板（全宽）、招聘列表、招聘详情、登录页均正常 |
| 注册 → 首页跳转 | 已用按契约实现的 mock 验证：填写学号与密码提交后自动登录并跳转首页，提示样式正常 |
| 管理员入口 | 管理员账号在首页与个人中心均可进入公告发布；普通账号不显示该入口（FR-09 要求） |
| 后端接口 | `backend/` 已合并 Sprint2 并应用全部迁移，`manage.py check` 无问题；`/announcements` 返回 401（需登录）、`/auth/register` 返回 400 校验错误，路由与数据表均正常 |

### 联调复跑步骤

1. 确认 `backend/` 为 Sprint2 代码（已合并 `backend_sprint2`），重启 `runserver`。
2. 按 `backend/.env.example` 配置数据库并执行 `python manage.py migrate`（新增 accounts/notifications/recruitments/applications/announcements 迁移）、`seed_tags`。
3. `python manage.py runserver 127.0.0.1:8000`。
4. 前端 `npm run dev`，使用同济邮箱注册一个普通账号；管理员用 `grant_admin` 授予。
5. 覆盖路径：注册/登录 → 首页公告 → 招聘筛选 → 投递（首次需确认个人信息处理告知）→ 发布者确认/拒绝 → 站内通知面板 → 撤回/修改申请 → 管理员治理下架。

## 6. 界面参考

| 桌面端首页（通知公告） | 小喇叭通知面板 |
| --- | --- |
| ![首页](../../../docs/frontend/images/home.png) | ![通知面板](../../../docs/frontend/images/notification-panel.png) |

登录页（学号 + 固定邮箱后缀）：![登录页](../../../docs/frontend/images/login.png)

移动端首页（390px）：![移动端首页](../../../docs/frontend/images/mobile-home.png)

## 7. 已知边界

- 后端列表接口不返回 `my_application`，招聘列表卡片无法标注「已申请」，详情页可见。
- `/announcements` 无关键词检索参数，公告页仅分页。
- 聊天为本地演示，未接后端；`email_notify_enabled` 不作为可用邮件开关展示。
- 公告/招聘的治理删除弹窗只校验 1–500 字，最终合法性仍由服务端判定。

## 8. 后续建议

1. 后端在 RecruitmentSummary 增加 `my_application`，前端即可在列表标注申请状态。
2. 聊天接口交付后，将 `data/mock/chatRepository.ts` 替换为 HTTP 实现，`MessageRepository` 端口与页面无需改动。
3. 公告补充 `q` 参数后，在首页增加搜索框。

## 9. 推送前整理（2026-11-16）

| 项 | 处理结果 |
| --- | --- |
| 后端合并 | `backend_sprint2` 内容原样并入 `backend/`（208 个源码文件逐文件 SHA-256 校验一致），保留 `.venv` 与 `var/` 运行数据；重复的解压目录已删除 |
| 迁移 | 已应用 `accounts.0002`、`announcements.0001`、`notifications.0002`、`recruitments.0003`、`applications.0002` |
| 重复文件 | 删除 `file/tasks` 下与 `docs/` 完全相同的需求文档 2 份；删除临时 mock/预览/截图脚本与截图 |
| 缓存与忽略 | 清理 `__pycache__`；`.gitignore` 增加 `__pycache__/`、`*.py[cod]`、`.venv/`、`backend/var/` |
| 文档 | README 更新为前后端合并后的仓库说明；本记录补充最终验收与整理结果 |
| 校验 | `tsc --noEmit` 0 error；`vite build` 通过；`manage.py check` 无问题 |
