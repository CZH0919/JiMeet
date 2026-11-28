# Sprint3 前端适配与交付记录

日期：2026-11-28｜前端分支：`main`（本轮改动位于工作区，尚未提交）｜对接基线：`backend-sprint3` 合并后的 `main`（`2d6a422`）与 `backend/design_file/api.md`（2026-11-23）
需求基线：[软件需求规格说明3.1](../../../file/tasks/软件需求规格说明3.1.md)、[修订说明与待确认事项](../../../file/tasks/修订说明与待确认事项.md) v1.4

## 1. 本轮范围

在已合并的 Sprint3 后端能力上完成前端适配、联调与 UI 收敛，**未修改 `backend/` 任何代码**。

| 需求 | 交付内容 | 主要页面 / 模块 |
| --- | --- | --- |
| FR-01 身份与准入 | 同济邮箱三步注册（发码 → 验码 → 设置密码）、密码/验证码双登录、验证码提示优先级、重发冷却与额度错误展示 | `LoginPage`、`useAuth`、`data/http/repository.ts` |
| FR-02 身份与权限 | 以详情 `permissions` 驱动按钮；管理员治理入口与基础身份入口分离；注销入口移至账号菜单 | `JobDetailPage`、`AppHeader`、`CancelAccountDialog` |
| FR-03 浏览与筛选 | 类型 / 标签 / 状态 / 关键词筛选、分页；用本人申请记录补上列表「已申请」状态 | `JobsPage`、`JobCard` |
| FR-04 简历上传 | PDF/DOC/DOCX、≤10 MiB、即时校验、随申请 multipart 提交；按 `can_download_resume` 控制预览与下载 | `FileUploader`、`ApplyDialog`、`ResumePreview` |
| FR-05 招聘管理 | 类型收敛为竞赛组队/校内活动、新增发布者补充说明、人数上限与截止时间校验、删除影响范围提示 | `JobFormPage`、`JobDetailPage`、`ProfilePage` |
| FR-06 状态变更 | 满员/关闭状态、申请处理窗口与按钮可用性以后端返回为准；非进行中招聘给出状态化提示 | `JobDetailPage`、`JobApplicationsPage` |
| FR-07 申请处理 | 投递、修改、撤回、确认/暂留/取消暂留/拒绝；撤回后可重新投递；修改已阅按 `seen_updated_at` 确认 | `JobApplicationsPage`、`ProfilePage` |
| FR-08 站内通知 | 新增投稿审核、公告删除、注销撤回等类型；按事件跳转对应列表与详情 | `NotificationBell`、`domain/labels.ts` |
| FR-09 公告与投稿 | 普通用户投稿前弹出规则确认、投稿表单、我的投稿；管理员直接发布、待审池领取/交回/通过/驳回、24 小时逾期高亮、待审红点 | `HomePage`、`AnnouncementFormPage`、`AdminPage`、`ProfilePage` |
| FR-10 站内聊天 | 移除本地演示仓储，接入真实会话/消息/未读/已读回执；新增对方主页与「聊一聊」入口 | `ChatPage`、`PeerProfilePage`、`data/http/chat.ts` |
| FR-11 管理员治理 | 招聘治理、公告治理、公告审核三个独立入口；原因必填并记录审计 | `AdminPage` |
| 3.5 账号注销 | 展示影响、勾选确认后调用 `DELETE /me`，成功后清空会话回登录页 | `CancelAccountDialog`、`useAuth` |

## 2. 关键实现说明

### 2.1 注册与登录

注册页改为三步，前端状态与后端会话资格保持一致：

1. 填写邮箱前缀（固定 `@tongji.edu.cn`）并调用 `POST /auth/register/send-code`；
2. 输入 6 位验证码并调用 `POST /auth/register/verify-code`；
3. 验码通过后展示姓名、昵称、身份、密码与确认密码，调用 `POST /auth/register`，成功后自动登录。

**提示优先级**（按需求确认）：

- 邮箱为空或格式错误时只提示邮箱；
- 未填写验证码时只提示「请输入验证码」，不请求验码接口；
- 验证码填写后才调用验码；此时服务端返回 `account_exists=true` 才提示「该邮箱已注册，请直接登录」，并提供「去登录该邮箱」与「换一个邮箱注册」；
- 验证码错误只提示验证码错误；建号时资格失效或并发邮箱冲突分别回到验证码步骤 / 提示登录；
- 验证码 5 分钟有效、同邮箱 60 秒重发冷却，倒计时以接口 `resend_after` 为准。

登录支持「密码登录」与「验证码登录」两种方式，验证码登录先调用 `POST /auth/login/send-code`。登录页不再提供开发调试登录入口，前端 `devLogin` 适配代码同步删除；`POST /auth/dev-login` 仅保留为后端隔离测试能力。

### 2.2 公告投稿与审核

- 首页「发布公告」对所有已登录用户可见：普通用户先看到投稿规则弹窗（仅竞赛/活动信息、需审核、预计 24 小时内处理、每日最多 5 条），确认后再进入投稿表单；管理员直接进入发布表单。
- 普通用户投稿调用 `POST /announcement-submissions`；审核通过后公告署名为审核管理员。投稿提交后不可改稿、撤回，个人中心「我的投稿」展示待审核/已通过/已驳回及驳回理由。
- 管理员「公告审核工作台」支持领取 15 分钟、交回、通过、驳回；领取批次 `claim_id` 在通过/交回/驳回时原样回传，锁冲突与已处理分别提示并刷新。超过 24 小时未处理的条目按后端排序置顶并高亮。
- 公告不可编辑（后端 PATCH 返回 405），前端移除编辑入口；旧 `/announcements/:id/edit` 链接重定向到详情。删除分为本人删除与治理删除两个入口。

### 2.3 站内聊天与对方主页

- 删除 `src/data/mock/chatRepository.ts` 及 `src/data/mock/` 目录，`data/index.ts` 全部走 HTTP。
- 会话列表按最近消息排序，展示对方昵称与未读数；消息页按时间正序渲染，使用 `before_id` 回翻历史，发送后按消息 id 合并并滚动到底部。
- 已读回执只提交页面实际展示的对方消息，批量上限 50 条；未读总数与站内通知未读数分别获取。
- 单条消息前端按 Unicode 码点限制 500，超出时禁用发送；后端 429 时展示 `retry_after` 并进入暂停发送倒计时。
- 新增 `/users/:uid` 对方主页：从招聘详情带 `recruitment_id`、从申请列表带 `application_id`；已有会话显示「继续聊天」，否则「聊一聊」创建或复用会话。

### 2.4 招聘、申请与注销

- 招聘类型只允许 `competition` / `activity`；历史 `internship` 记录仍按后端展示为活动招聘。
- 招聘新增「补充说明」字段（≤1000 字），详情单独展示；与申请时填写的说明区分。
- 删除招聘前如为发布者，读取详情 `application_counts` 计算处理中 + 已接受数量，二次确认中说明受影响范围。
- 招聘列表通过 `GET /me/applications` 建立「招聘 → 最近一次申请」映射，为卡片补充「已申请 · 状态」；撤回后允许重新投递，详情不再因 `withdrawn` 阻止申请。
- 账号注销入口移至右上账号菜单「退出登录」下方，弹窗展示影响并使用勾选确认；成功后清空本地登录态并回到登录页。

## 3. UI 与文案收敛

1. **统一栏宽**：`.page-shell` 统一为 `1120px`，移除各页面单独设置的 720/820/900/1000/1100 宽度，所有页面主栏与页头左右边界一致。
2. **返回按钮对齐**：招聘详情、招聘表单、申请管理、公告详情、投稿、对方主页等页面均使用同一 `page-shell` 左边界与顶部间距。
3. **注销入口**：从个人中心底部移除，收敛到右上账号菜单，减少个人中心纵向堆叠。
4. **文案精简**：删除重复、口语化的小字说明，保留字数、格式、隐私、审核时限等必要规则；首页副标题、招聘详情不可投递原因、消息空态、错误提示等改为面向对象的短句。
5. **移除开发调试登录**：登录/注册页底部整块删除，并清理前端 `devLogin` 仓储方法与 `useAuth` 暴露。
6. **登录页左侧介绍**：按最终确认恢复为原介绍段落与三条要点，保留本次注册流程与页面宽度调整。

## 4. 代码结构整理

新增：

- `src/pages/PeerProfilePage.tsx`：对方主页与聊天入口。
- `src/data/http/chat.ts`：对方主页与聊天的 HTTP 仓储。
- `src/components/account/CancelAccountDialog.tsx`：注销影响说明与确认弹窗。
- `src/components/announcement/PublishAnnouncementButton.tsx`：发布公告 / 投稿规则弹窗。
- `src/features/useSubmissionReview.ts`：管理员待审数量轮询（红点）。

调整：

- `src/data/index.ts` 改为全部 HTTP 仓储，删除对本地 mock 聊天的依赖。
- `src/data/ports.ts`、`src/data/http/repository.ts`、`src/data/http/mappers.ts` 补齐账号、投稿审核、聊天、注销相关端口与映射。
- `src/domain/models.ts`、`validation.ts`、`labels.ts`、`permissions.ts`、`jobStatus.ts` 同步新字段、状态与校验。
- `src/App.tsx` 新增 `/users/:uid`、`/messages/:conversationId`，调整公告投稿路由与旧编辑链接。
- `README.md` 更新为当前前后端能力、启动步骤与已知边界。

删除：

- `src/data/mock/chatRepository.ts` 及 `src/data/mock/` 目录。
- 前端 `devLogin` 相关类型、方法与页面入口。

## 5. 接口对接清单

| 方法 | 路径 | 前端调用点 |
| --- | --- | --- |
| GET | `/auth/csrf` | `data/http/client.ts#fetchCsrf`（启动、发码、登录、注册、登出后） |
| POST | `/auth/register/send-code`、`/verify-code`、`/auth/register` | 三步注册 |
| POST | `/auth/login/send-code`、`/auth/login` | 密码 / 验证码登录 |
| POST | `/auth/logout`、`GET /me`、`PATCH /me`、`DELETE /me` | 会话、资料、注销 |
| POST | `/me/privacy-consent` | 首次投递前确认告知 |
| GET | `/tags`、`/recruitments`、`/recruitments/{id}`、`/me/recruitments` | 招聘列表、详情、我的发布 |
| POST/PATCH/DELETE | `/recruitments`、`/recruitments/{id}`、`/close`、`/admin/recruitments/{id}` | 发布、编辑、关闭、本人/治理删除 |
| POST/GET | `/recruitments/{id}/applications`、`/me/applications`、`/applications/{id}` | 投递、申请列表、详情 |
| PATCH/POST | `/applications/{id}`、`/withdraw`、`/accept`、`/reject`、`/hold`、`/unhold`、`/read` | 修改、撤回、处理、已阅确认 |
| GET | `/applications/{id}/resume` | 简历预览 / 下载（文件流） |
| GET | `/announcements`、`/announcements/{id}` | 首页、公告详情 |
| POST/DELETE | `/announcements`、`/announcements/{id}`、`/admin/announcements/{id}` | 管理员发布、本人删除、治理删除 |
| POST/GET | `/announcement-submissions`、`/me/announcement-submissions` | 投稿、我的投稿 |
| GET/POST | `/admin/announcement-submissions`、`/{id}/claim`、`/release`、`/approve`、`/reject` | 待审池、领取、交回、通过、驳回 |
| GET | `/notifications`、`/unread-count`、`/users/{uid}` | 通知、未读、对方主页 |
| GET/POST | `/chat/conversations`、`/messages`、`/read`、`/unread-count` | 会话、历史、发送、回执、未读 |

## 6. 验收记录

| 项 | 结果 |
| --- | --- |
| `npm run typecheck`（strict + noUnusedLocals） | 通过，0 error |
| `npm run build` | 通过；`dist/index.html` 0.58 kB，CSS 32.92 kB（gzip 6.81 kB），JS 345.84 kB（gzip 104.59 kB） |
| 真实后端联调 | 使用仓库内后端、开发数据库与临时本地 TLS SMTP，完整走通注册、登录、投稿审核、聊天、招聘补充说明与删除 |
| 注册流程 | 三步注册成功；缺少验证码只提示验证码；已注册邮箱在验码后才提示并提供登录入口；密码登录与验证码登录均成功 |
| 公告流程 | 规则弹窗 → 投稿 → 我的投稿「待审核」；管理员领取并页面通过 → 首页显示；驳回、交回、旧批次 409、治理删除通过接口复验 |
| 聊天流程 | 对方主页 → 创建/复用会话 → 发送消息 → 未读数 → 已读回执（重复回执为 0）→ 历史 `before_id` 回翻 |
| 招聘流程 | 发布带补充说明的招聘 → 详情展示 → 二次确认删除；列表「已申请」映射已实现，未用真实投递数据逐页复验 |
| 注销流程 | 账号菜单入口、影响说明与勾选确认可用；`DELETE /me` 返回 200，成功后前端清空登录态并跳转登录页 |
| 页面宽度 | 登录页及首页、招聘列表、招聘详情、招聘表单、投稿、个人中心、消息、对方主页共 9 个页面实测 `left=69, width=1120` |
| 浏览器异常 | 最终复跑无页面 JS 异常；403 页面、普通用户访问治理后台拦截正常 |

### 联调步骤

1. 后端切换/更新到包含 Sprint3 的 `main`，执行一次 `python manage.py migrate` 与 `python manage.py seed_tags`。
2. 在同一后端 PowerShell 配置 SMTP 与 HMAC 环境变量（变量名见 `backend/.env.example`；Django 不自动读取 `.env`），再运行 `python manage.py runserver 127.0.0.1:8000`。
3. 前端 `npm run dev`，Vite 按 `.env` 的 `DEV_API_TARGET=http://127.0.0.1:8000` 代理 `/api/v1`。
4. 用同济邮箱完成注册；管理员账号通过 `grant_admin --email ...` 授予后进入「公告审核工作台」。
5. 覆盖顺序：注册/登录 → 首页公告/投稿审核 → 招聘发布（含补充说明）→ 投递/修改/撤回/处理 → 聊天 → 通知 → 注销。

### 联调数据说明

为验证注册与投稿审核，开发数据库新增了 `fe-register-*`、`fe-chat-*` 等测试账号及少量「【前端自测】」软删除数据；测试用管理员权限已撤销，公开首页未保留测试公告。生产/验收环境不需要这些数据。

## 7. 已知边界

- 公告不支持编辑（后端 405），如需更正只能删除后重新发布。
- 招聘列表的「已申请」由前端额外拉取 `/me/applications` 计算，招聘数量与申请数量较大时会多一次分页请求。
- `email_notify_enabled` 为兼容字段，不代表可用的邮件通知开关；业务通知仅站内投递。
- 聊天消息按后端六个月规则清理；前端不缓存历史。
- 未配置 SMTP 时，注册发码与验证码登录返回 503，页面提示「邮件发送服务暂时不可用，请稍后重试」；已有账号密码登录不受影响。
- 账号不提供在线密码重置；如需处理历史无密码账号，由管理员使用受控命令。
- 学校 SSO 两个入口仍返回 501。

## 8. 后续建议

1. 若后端在 RecruitmentSummary 中补充 `my_application`，可移除前端额外的申请映射请求。
2. 生产环境将 SMTP 故障探测与 `check_registration_mail` 纳入定时任务和告警。
3. 公告增加关键词检索参数后，可在首页补充搜索框。
4. 增加前端单元测试或 Playwright 用例，覆盖注册提示优先级、审核锁冲突与聊天限流。

## 9. 交付物

- 前端源码：`src/`（修改 29 个文件、删除 1 个 mock 聊天文件、新增 5 个文件/目录）；另更新根目录 README 并新增本记录。
- 交付说明：本记录；根目录 [README.md](../../../README.md) 同步更新。
- 接口契约：`backend/design_file/api.md`（未修改，作为唯一正文）。
- 运行手册：`backend/deploy/README.md`（未修改）。
