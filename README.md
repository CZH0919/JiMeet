# 济遇 · 校内竞赛与活动招聘平台

面向同济大学师生的竞赛组队、校内活动招聘与公告平台。
仓库包含 React 前端与 Django 后端。页面已全部接入 Sprint 3 后端：同济邮箱验证码注册、密码/验证码登录、公告投稿与审核工作台、对方主页与站内聊天、账号注销。[前端交接说明](Project_Progress_Record/Sprint3_BackEnd/Record/frontend_handoff.md)

## 1. 当前状态

| 功能域 | 数据来源 | 说明 |
| --- | --- | --- |
| 注册 / 登录 / 会话 | 后端 `/auth/register/send-code`、`/auth/register/verify-code`、`/auth/register` 及登录、会话接口 | 三步注册（邮箱 → 验证码 → 设置密码）；已注册邮箱只在验码成功后提示；支持密码或验证码登录，使用 CSRF 和 Session Cookie |
| 个人资料 | 后端 `GET/PATCH/DELETE /me`、`POST /me/privacy-consent` | 支持昵称修改与隐私确认；账号注销位于右上账号菜单（影响说明 + 二次确认） |
| 通知公告（首页） | 后端 `/announcements`、`/announcement-submissions` | 首页即公告页，按发布时间倒序分页；普通用户先看投稿规则再投稿，管理员直接发布或领取审核；公告发布后不可编辑 |
| 招聘 | 后端 `/recruitments`、`/me/recruitments`、`/tags` | 类型/标签/状态/关键词筛选，分页；支持发布者补充说明 |
| 申请与简历 | 后端 `/me/applications`、`/recruitments/{id}/applications`、`/applications/{id}` 等 | 上传 PDF/DOC/DOCX（≤10 MiB）、修改、撤回、确认/暂留/拒绝、下载 |
| 站内通知 | 后端 `/notifications` | 页头小喇叭 + 右侧通知面板；覆盖投稿审核、公告删除、招聘与申请事件 |
| 管理员治理 | 后端 `DELETE /admin/recruitments/{id}`、`DELETE /admin/announcements/{id}` | 独立入口、原因必填、通知发布者并写审计；另有公告审核工作台（待审红点） |
| 站内聊天 | 后端 `/chat/conversations`、`/users/{uid}` | 一对一纯文本；招聘详情与申请列表进入对方主页发起；未读、分页回翻与已读回执 |

接口契约以 [`backend/design_file/api.md`](backend/design_file/api.md) 为唯一正文。

## 2. 页面与导航

首页展示竞赛与活动公告，可切换到招聘、个人中心和消息。头像旁的通知面板展示申请结果、投稿审核、招聘变化和治理消息，支持单条或全部已读。管理员在首页与账号菜单均可进入带待审红点的公告审核工作台。

## 3. 技术栈

React 18 · TypeScript 5 · Vite 5 · Tailwind CSS 3 · React Router 6 · Zustand 5 · lucide-react

## 4. 快速开始

### 4.1 启动后端

开发环境使用 PostgreSQL 并按 `backend/.env.example` 设置进程环境变量。Django 不自动加载 `.env`。从仓库根目录执行：

```bash
cd backend
python -m pip install -r requirements/base.txt
python manage.py migrate       # 拉取 Sprint 3 代码后需执行一次（注册验证码、聊天、注销等表）
python manage.py seed_tags
python manage.py runserver 127.0.0.1:8000
```

**启动方式与之前相同**：已有的管理员 PowerShell 启动 PostgreSQL、后端 `runserver` 与前端 `npm run dev` 三套命令都不变；仅在拉取本次后端 Sprint 3 合并后，首次启动前补一次 `python manage.py migrate`。若 SMTP 环境变量尚未配置，注册发码会返回 503「邮件发送服务暂时不可用」，已有账号仍可凭密码登录。

生产镜像、HTTPS 代理、迁移、定时任务及备份恢复见[后端运行手册](backend/deploy/README.md)。

### 4.2 启动前端

```bash
npm install
npm run dev        # http://localhost:5173
npm run typecheck  # tsc --noEmit
npm run build      # 生产构建（tsc + vite build）
npm run preview    # 预览构建产物
```

前端统一请求相对路径 `/api/v1/...`，由 Vite 代理转发到 `DEV_API_TARGET`（默认 `http://127.0.0.1:8000`，见 `.env`）。
代理保留 Host、Origin 与 Cookie，因此 CSRF 与同源会话可直接工作。

### 4.3 注册与登录

- 注册页按三步进行：填写同济邮箱并获取验证码 → 输入 6 位验证码 → 设置密码与身份资料。接口顺序见 [API 正文 4.3](backend/design_file/api.md#43-邮箱验证码注册)。
- 提示优先级：邮箱格式错误只提示邮箱；缺少验证码只提示验证码；**只有验证码校验成功后**，服务端才会告知该邮箱已注册，页面随后提供「去登录该邮箱」入口，不会在建号前泄露注册状态。
- 验证码 5 分钟有效，同一邮箱 60 秒内只能请求一次；注册与登录验证码共享该重发间隔。发码失败或额度超限时页面会展示具体原因。
- 已有账号可在 `/login` 使用密码或邮箱验证码登录；退出后原会话失效。忘记密码暂不提供在线重置，需由管理员处理。
- 启用注册投递时按 `backend/.env.example` 配置发件地址、SMTP 专用密码与至少 32 字符的独立随机 HMAC 密钥。SMTP 使用 465 端口的隐式 TLS。
- 登录页不再提供开发调试登录入口；开发联调使用正式注册或已有账号密码登录，`POST /auth/dev-login` 仅保留为后端隔离测试能力。
- 管理员可直接发布公告，普通用户通过投稿交由管理员审核。部署人员可按邮箱授予或撤销业务管理员权限：

```bash
cd backend
python manage.py grant_admin --email 2151234@tongji.edu.cn
# 撤销：python manage.py revoke_admin --email 2151234@tongji.edu.cn
```

管理员可在「个人中心 → 管理员功能」、首页「公告审核工作台」或账号菜单进入公告审核与内容治理。

### 4.4 本地自检

```bash
npm run typecheck                 # 前端类型检查（strict + noUnusedLocals）
npm run build                     # 生产构建
cd backend && python manage.py check   # Django 系统检查
```

## 5. 目录结构

```
.
├─ src/                        前端源码（React + TS + Vite）
├─ public/                     静态资源（logo.png / favicon）
├─ backend/                    Django 后端、部署配置与接口文档
├─ Project_Progress_Record/    各迭代的正式计划与交付记录
├─ file/                       开发环境配置与需求整理资料
├─ dist/                       前端构建产物（gitignore）
└─ .env                        Vite 代理目标（DEV_API_TARGET）
```

前端 `src/` 内部结构：

```
src/
├─ pages/                     路由页面（1:1）
│  ├─ HomePage.tsx            首页：公告列表 / 发布公告 / 审核工作台入口
│  ├─ AnnouncementDetailPage.tsx
│  ├─ AnnouncementFormPage.tsx 管理员发布公告 / 普通用户投稿
│  ├─ JobsPage.tsx            招聘列表与筛选
│  ├─ JobDetailPage.tsx       招聘详情 / 申请入口 / 聊一聊 / 治理区
│  ├─ JobFormPage.tsx         发布与编辑招聘（含补充说明）
│  ├─ JobApplicationsPage.tsx 发布者申请管理 / 联系申请人
│  ├─ PeerProfilePage.tsx     对方主页（公开资料与聊天入口）
│  ├─ ProfilePage.tsx         个人中心（我发布的 / 收到的 / 我提交的 / 我的投稿）
│  ├─ AdminPage.tsx           内容治理后台（招聘 / 公告 / 公告审核）
│  ├─ ChatPage.tsx            站内消息（后端会话、回翻与已读回执）
│  ├─ LoginPage.tsx           登录（密码/验证码）与三步注册
│  └─ ErrorPages.tsx          403 / 404
├─ components/
│  ├─ layout/                 AppHeader、Logo、NotificationBell（小喇叭）
│  ├─ ui/                     Button、Field、Modal、ConfirmDialog、StatusBadge、Pagination、Feedback、ToastHost
│  ├─ job/                    JobCard、JobTypeTag、QuotaProgress
│  ├─ announcement/           PublishAnnouncementButton（投稿规则弹窗）
│  ├─ account/                CancelAccountDialog（注销确认）
│  ├─ application/            ApplyDialog、EditApplicationDialog、FileUploader、ResumePreview
│  └─ guards.tsx              路由守卫（RequireAuth / RequireAdmin）
├─ features/                  useAuth、useJobs、useNotifications、useSubmissionReview、useAsync
├─ domain/                    纯函数领域层
│  ├─ models.ts               领域模型（对齐后端契约）
│  ├─ labels.ts               枚举 → 中文文案唯一真源
│  ├─ format.ts               时间与剩余时长格式化
│  ├─ jobStatus.ts            招聘状态机 / 可否申请
│  ├─ permissions.ts          权限判定兜底
│  └─ validation.ts           表单 / 文件 / 账号校验
├─ data/
│  ├─ ports.ts                Repository 端口（UI 只依赖这些接口）
│  ├─ index.ts                依赖注入唯一开关（全部走后端 HTTP）
│  ├─ fetchAll.ts             按后端每页上限循环拉取
│  └─ http/                   API 客户端、DTO 映射、主仓储与聊天仓储（chat.ts）
└─ stores/                    Zustand（session / toast）
```

## 6. 与后端对接的关键约定

- 统一信封 `{ code, message, data, request_id }`；分页 `{ items, page, page_size, total }`，`page_size` 上限 50。
- `sessionid` 为 HttpOnly Cookie，`fetch` 使用 `credentials: 'same-origin'`；写请求带 `X-CSRFToken`。
- 登录/注册成功后重新 `GET /auth/csrf` 刷新令牌（后端会轮换 CSRF 密钥）。
- 权限以详情接口返回的 `permissions` 为准（`can_apply`、`can_edit`、`can_delete`、`can_govern_delete` 等）；前端只做展示，写请求仍由服务端校验。
- 招募删除分两个入口：`DELETE /recruitments/{id}`（本人）与 `DELETE /admin/recruitments/{id}`（治理，原因必填）。
- 申请详情读取**不清除** `has_unseen_update`；展示后调用 `POST /applications/{id}/read` 并传 `seen_updated_at` 确认已阅。
- 注册必须在同一会话内按「发码 → 验码 → 建号」顺序调用；验码成功前不提示邮箱是否已注册。
- 聊天历史按 `before_id` 回翻，已读回执只提交页面实际展示的对方消息；未读数与站内通知分别统计。
- 通知已读与申请已阅相互独立；`target_is_deleted` 只表示关联对象已删除，不代表申请状态。

## 7. 已知边界

| 项 | 说明 |
| --- | --- |
| 注册发码 503 | 未配置 SMTP 或投递失败时返回「邮件发送服务暂时不可用」。按 `backend/.env.example` 配置 `JIMEET_SMTP_*` 与 `JIMEET_REGISTRATION_HMAC_KEY` 后重启后端；已有账号不受影响 |
| 验证码重发 | 注册与登录验证码共享同一邮箱 60 秒冷却和发送额度；页面倒计时仅覆盖当前流程，服务端仍以额度为准 |
| 公告编辑 | 后端对公告 PATCH 返回 405，前端已移除编辑入口；已发布公告需删除后重新发布 |
| 邮件通知 | 业务通知使用站内渠道。`email_notify_enabled` 为兼容字段，不控制注册验证码 |
| 学校 SSO | 两个 SSO 入口返回 501；正式注册通过同济邮箱验证码验证归属 |
| 公告关键词搜索 | 后端 `/announcements` 未提供 `q` 参数，前端只做分页 |
| 聊天留存 | 消息按服务端六个月规则清理；前端不缓存历史，刷新后以接口为准 |

## 8. 交付记录

- Sprint 2 前端适配与验收记录：[`Project_Progress_Record/Sprint2_FrontEnd/Record/frontend_sprint2_delivery.md`](Project_Progress_Record/Sprint2_FrontEnd/Record/frontend_sprint2_delivery.md)
- Sprint 3 前端适配与交付记录：[`Project_Progress_Record/Sprint3_FrontEnd/Record/frontend_sprint3_delivery.md`](Project_Progress_Record/Sprint3_FrontEnd/Record/frontend_sprint3_delivery.md)
- 后端交付说明：[Sprint 3 最终交付](Project_Progress_Record/Sprint3_BackEnd/Record/stage_06_delivery.md)
- 需求文档：[软件需求规格说明 3.1](file/tasks/软件需求规格说明3.1.md)
