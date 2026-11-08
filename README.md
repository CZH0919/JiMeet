# 济遇 · 校内招聘平台（前端）

面向同济大学校内师生的 Web 端竞赛组队 / 校内活动 / 实验室实习招聘平台。

## 当前状态

前端已接入后端（Sprint2 迁移成果），采用**混合仓储**：

| 功能 | 数据来源 |
| --- | --- |
| 登录 / 个人资料 | 后端（dev-login + `/me`） |
| 招聘（竞赛 / 活动 / 实习）、标签 | 后端 `/recruitments`、`/tags` |
| 申请（投递 / 修改 / 撤回 / 处理 / 简历下载） | 后端 `/applications` 等 |
| 站内通知 | 后端 `/notifications` |
| 管理员内容治理 | 后端 `DELETE /recruitments/{id}` |
| 竞赛通知 | **本地 mock**（后端暂未提供该类型） |
| 站内聊天 | **本地 mock**（后端暂未提供） |

后端接口契约以 [backend/design_file/api.md](backend/design_file/api.md) 为准。

## 技术栈

React 18 + TypeScript 5 + Vite 5 + Tailwind CSS 3 + React Router 6 + Zustand 5 + lucide-react

## 快速开始

### 1. 启动后端

后端代码见 `backend/`（Django 6.1 + PostgreSQL 15+，Python 3.12+）：

```bash
cd backend
# 按 backend/.env.example 配置环境变量（DB 等），执行迁移与标签初始化
python manage.py migrate
python manage.py seed_tags
python manage.py runserver 127.0.0.1:8000
```

后端环境变量清单与运行约定见 [api.md §1.1](backend/design_file/api.md) 与 `backend/.env.example`。开发登录需 `DEBUG=true` 且 `ALLOW_DEV_LOGIN=true`。

### 2. 启动前端

```bash
npm install
npm run dev        # http://localhost:5173
npm run typecheck  # tsc --noEmit
npm run build      # 生产构建
```

前端通过 Vite 开发代理把 `/api/v1/*` 转发到后端（同源，保留 Cookie 与 CSRF 校验）。代理目标由 `.env` 的 `DEV_API_TARGET` 指定，默认 `http://127.0.0.1:8000`。

### 3. 登录

开发阶段使用编号登录（后端 dev-login）：输入一个 `real_id`（1~32 位字母/数字/下划线/短横线），**以 `t`/`T` 开头映射为教师**，其余为学生。首次使用会自动创建开发身份。正式统一身份认证尚未接入（预留 501）。

## 目录结构

```
src/
├─ pages/              页面（按路由 1:1）
├─ components/
│  ├─ ui/              基础组件
│  ├─ layout/          布局（AppHeader/Logo/NotificationDrawer）
│  ├─ job/             招聘卡片/类型标签/人数进度
│  └─ application/     申请弹层/文件上传
├─ features/           功能 hooks（useAuth/useJobs/useNotifications/useAsync）
├─ domain/             领域层（纯函数，无 IO，可单测）
│  ├─ models.ts        领域模型（对齐后端契约）
│  ├─ jobStatus.ts     招聘状态机 / 能否申请判定
│  ├─ applicationStatus.ts  申请状态机
│  ├─ permissions.ts   权限判定
│  ├─ labels.ts        枚举→中文文案唯一真源
│  └─ validation.ts    表单/文件校验
├─ data/
│  ├─ ports.ts         Repository 端口（UI 只依赖这些接口）
│  ├─ index.ts         混合仓储组装（唯一 DI 开关）
│  ├─ http/            HttpRepository + mapper + API 客户端（接后端）
│  └─ mock/            本地 mock（仅竞赛通知 + 聊天）
└─ stores/             Zustand（session / toast）
```

## 与后端对接的关键约定

- 请求统一走 `/api/v1`，由 Vite 代理转发，页面不硬编码后端地址。
- Session 为 HttpOnly Cookie，`fetch` 使用 `credentials: 'same-origin'`；写请求携带 `X-CSRFToken`（登录前先 `GET /auth/csrf`，登录后再次刷新）。
- JSON 字段 `snake_case`；后端返回统一信封 `{code, message, data, request_id}`；分页 `{items, page, page_size, total}`。
- 后端 DTO → 领域模型的映射集中在 `src/data/http/mappers.ts`，领域层与 UI 层不感知后端字段差异。
- 后端未提供的功能（竞赛通知、聊天）保留在 `src/data/mock/`，由 `src/data/index.ts` 路由分发。

## 关键业务规则

- 简历仅 PDF / DOC / DOCX，单文件 ≤ 10 MB；随申请 multipart 一起提交（无独立上传接口）。
- 申请 5 态：处理中 / 已接受 / 已拒绝 / 已撤回 / 已失效，后四者终态不可变更。
- 发布者标记 3 种：确认 → 已接受、暂留 → 处理中（私有）、拒绝 → 已拒绝。
- 满员优先于到期；不可申请本人招聘；不可重复申请；提交申请前须确认个人信息处理告知。
- 学生可发布竞赛组队；教师可发布活动招聘 / 实验室实习 / 竞赛通知。
- 管理员治理删除须填写原因；管理员不增加申请内容或简历读取权限。
