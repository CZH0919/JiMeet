# 济遇 · 校内竞赛与活动招聘平台

面向同济大学师生的竞赛组队、校内活动招聘与公告平台。
仓库包含 React 前端与 Django 后端。已有页面接入招聘、申请和站内通知；验证码注册与登录、公告投稿审核、站内聊天和账号注销的页面适配见[前端交接说明](Project_Progress_Record/Sprint3_BackEnd/Record/frontend_handoff.md)。

## 1. 当前状态

| 功能域 | 数据来源 | 说明 |
| --- | --- | --- |
| 注册 / 登录 / 会话 | 后端 `/auth/register/send-code`、`/auth/register/verify-code`、`/auth/register` 及登录、会话接口 | 同济邮箱验证码注册，支持密码或验证码登录，使用 CSRF 和 Session Cookie |
| 个人资料 | 后端 `GET/PATCH/DELETE /me`、`POST /me/privacy-consent` | 支持昵称修改、隐私确认与本人注销。注销确认页面待前端接入 |
| 通知公告（首页） | 后端 `/announcements` | 首页即公告页，按发布时间倒序分页；普通用户可投稿，管理员直接发布或领取审核，公告发布后不可编辑 |
| 招聘 | 后端 `/recruitments`、`/me/recruitments`、`/tags` | 类型/标签/状态/关键词筛选，分页 |
| 申请与简历 | 后端 `/me/applications`、`/recruitments/{id}/applications`、`/applications/{id}` 等 | 上传 PDF/DOC/DOCX（≤10 MiB）、修改、撤回、确认/暂留/拒绝、下载 |
| 站内通知 | 后端 `/notifications` | 页头小喇叭 + 右侧通知面板（已移除通知分页页） |
| 管理员治理 | 后端 `DELETE /admin/recruitments/{id}`、`DELETE /admin/announcements/{id}` | 独立入口、原因必填、通知发布者并写审计 |
| 站内聊天 | **本地演示数据**（`src/data/mock/chatRepository.ts`） | 当前页面使用演示数据，后端[对方主页与聊天接口](backend/design_file/api.md#10-对方主页与站内聊天)已可对接 |

接口契约以 [`backend/design_file/api.md`](backend/design_file/api.md)为唯一正文。

## 2. 页面与导航

首页展示竞赛与活动公告，可切换到招聘、个人中心和消息。头像旁的通知面板展示申请结果、招聘变化和治理消息，支持单条或全部已读。

## 3. 技术栈

React 18 · TypeScript 5 · Vite 5 · Tailwind CSS 3 · React Router 6 · Zustand 5 · lucide-react

## 4. 快速开始

### 4.1 启动后端

开发环境使用 PostgreSQL 并按 `backend/.env.example` 设置进程环境变量。Django 不自动加载 `.env`。从仓库根目录执行：

```bash
cd backend
python -m pip install -r requirements/base.txt
python manage.py migrate
python manage.py seed_tags
python manage.py runserver 127.0.0.1:8000
```

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

- 已有账号可在 `/login` 登录。新账号注册的后端调用顺序为申请验证码、验证邮箱、设置密码并建号，见 [API 正文 4.3](backend/design_file/api.md#43-邮箱验证码注册)。当前注册表单尚未接入发码和验码。
- 启用注册投递时按 `backend/.env.example` 配置发件地址、SMTP 专用密码与至少 32 字符的独立随机 HMAC 密钥。SMTP 使用 465 端口的隐式 TLS。
- 开发联调时登录页底部提供「开发调试登录」（仅 `import.meta.env.DEV` 可见，调用后端 `POST /auth/dev-login`），**不得用于正式验收**。
- 管理员可直接发布公告，普通用户通过投稿交由管理员审核。部署人员可按邮箱授予或撤销业务管理员权限：

```bash
cd backend
python manage.py grant_admin --email 2151234@tongji.edu.cn
# 撤销：python manage.py revoke_admin --email 2151234@tongji.edu.cn
```

管理员可在「个人中心 → 管理员功能」或首页右上角进入公告发布与内容治理。

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
│  ├─ HomePage.tsx            首页：通知公告列表
│  ├─ AnnouncementDetailPage.tsx
│  ├─ AnnouncementFormPage.tsx
│  ├─ JobsPage.tsx            招聘列表与筛选
│  ├─ JobDetailPage.tsx       招聘详情 / 申请入口 / 治理区
│  ├─ JobFormPage.tsx         发布与编辑招聘
│  ├─ JobApplicationsPage.tsx 发布者申请管理
│  ├─ ProfilePage.tsx         个人中心（我发布的 / 收到的 / 我提交的）
│  ├─ AdminPage.tsx           内容治理后台（招聘 / 公告）
│  ├─ ChatPage.tsx            站内消息（演示数据）
│  ├─ LoginPage.tsx           登录 / 注册
│  └─ ErrorPages.tsx          403 / 404
├─ components/
│  ├─ layout/                 AppHeader、Logo、NotificationBell（小喇叭）
│  ├─ ui/                     Button、Field、Modal、ConfirmDialog、StatusBadge、Pagination、Feedback、ToastHost
│  ├─ job/                    JobCard、JobTypeTag、QuotaProgress
│  ├─ application/            ApplyDialog、EditApplicationDialog、FileUploader
│  └─ guards.tsx              路由守卫（RequireAuth / RequireAdmin）
├─ features/                  useAuth、useJobs、useNotifications、useAsync
├─ domain/                    纯函数领域层
│  ├─ models.ts               领域模型（对齐后端契约）
│  ├─ labels.ts               枚举 → 中文文案唯一真源
│  ├─ format.ts               时间与剩余时长格式化
│  ├─ jobStatus.ts            招聘状态机 / 可否申请
│  ├─ permissions.ts          权限判定兜底
│  └─ validation.ts           表单 / 文件 / 账号校验
├─ data/
│  ├─ ports.ts                Repository 端口（UI 只依赖这些接口）
│  ├─ index.ts                依赖注入唯一开关（HTTP + 本地演示聊天）
│  ├─ fetchAll.ts             按后端每页上限循环拉取
│  ├─ http/                   API 客户端、DTO 映射、HTTP 仓储
│  └─ mock/                   仅站内聊天演示仓储
└─ stores/                    Zustand（session / toast）
```

## 6. 与后端对接的关键约定

- 统一信封 `{ code, message, data, request_id }`；分页 `{ items, page, page_size, total }`，`page_size` 上限 50。
- `sessionid` 为 HttpOnly Cookie，`fetch` 使用 `credentials: 'same-origin'`；写请求带 `X-CSRFToken`。
- 登录/注册成功后重新 `GET /auth/csrf` 刷新令牌（后端会轮换 CSRF 密钥）。
- 权限以详情接口返回的 `permissions` 为准（`can_apply`、`can_edit`、`can_delete`、`can_govern_delete` 等）；前端只做展示，写请求仍由服务端校验。
- 招募删除分两个入口：`DELETE /recruitments/{id}`（本人）与 `DELETE /admin/recruitments/{id}`（治理，原因必填）。
- 申请详情读取**不清除** `has_unseen_update`；展示后调用 `POST /applications/{id}/read` 并传 `seen_updated_at` 确认已阅。
- 通知已读与申请已阅相互独立；`target_is_deleted` 只表示关联对象已删除，不代表申请状态。

## 7. 已知边界

| 项 | 说明 |
| --- | --- |
| 首页/注册提示「接口不存在（HTTP 404）」 | 确认前端代理指向已提供对应接口的后端实例，并核对注册三步接口路径 |
| 站内聊天 | 当前页面仍使用本地演示数据。接入第 10 章的聊天接口后，消息将写入后端数据库 |
| 招聘列表的「已申请」标记 | 后端列表接口（RecruitmentSummary）不返回 `my_application`，列表卡片无法标注申请状态；详情页会显示 |
| 邮件通知 | 业务通知使用站内渠道。`email_notify_enabled` 为兼容字段，不控制注册验证码 |
| 学校 SSO | 两个 SSO 入口返回 501；正式注册通过同济邮箱验证码验证归属 |
| 公告关键词搜索 | 后端 `/announcements` 未提供 `q` 参数，前端只做分页 |

## 8. 交付记录

- Sprint 2 前端适配与验收记录：[`Project_Progress_Record/Sprint2_FrontEnd/Record/frontend_sprint2_delivery.md`](Project_Progress_Record/Sprint2_FrontEnd/Record/frontend_sprint2_delivery.md)
- 后端交付说明：[Sprint 3 最终交付](Project_Progress_Record/Sprint3_BackEnd/Record/stage_06_delivery.md)
- 需求文档：[软件需求规格说明 3.1](file/tasks/软件需求规格说明3.1.md)
