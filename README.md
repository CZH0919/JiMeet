# 济遇 · 校内招聘平台（前端）

面向同济大学校内师生的 Web 端竞赛组队 / 校内活动招聘平台。本仓库为**纯前端**，后端未就绪，当前以 Mock 驱动（见 [EXEC_PLAN.md](./EXEC_PLAN.md) 的「VGA / 转接头」架构）。

## 技术栈

React 18 + TypeScript 5 + Vite 5 + Tailwind CSS 3 + React Router 6 + Zustand 5 + lucide-react

## 快速开始

```bash
npm install
npm run dev        # http://localhost:5173
npm run typecheck  # tsc --noEmit
npm run build      # 生产构建（tsc + vite build）
```

## Mock 说明（后端未就绪阶段）

- 默认 `VITE_USE_MOCK=true`（见 `.env`），数据层走内存 + `localStorage` 持久化，刷新不丢。
- 登录页提供「演示模式 · 快速切换身份」，可一键切换学生 / 教师 / 管理员：

| 身份 | 账号（邮箱） | 说明 |
|---|---|---|
| 张同学 | zhang@tongji.edu.cn | 学生 + 管理员（唯一管理员） |
| 李同学 | li@tongji.edu.cn | 学生 |
| 赵同学 | zhao@tongji.edu.cn | 学生 |
| 陈同学 | chen@tongji.edu.cn | 学生 |
| 王老师 | wang@tongji.edu.cn | 教师 |
| 刘老师 | liu@tongji.edu.cn | 教师 |

- 控制台调试辅助（仅 dev 构建）：

```js
window.__mock.reset()   // 重置 Mock 数据
window.__mock.users()   // 查看全部用户
```

## 目录结构

```
src/
├─ pages/            页面（按路由 1:1）
├─ components/
│  ├─ ui/            基础组件（Button/Modal/Field/Feedback/Pagination/StatusBadge/…）
│  ├─ layout/        布局（AppHeader/Logo/NotificationDrawer）
│  ├─ job/           招聘卡片/标签/人数进度
│  └─ application/   申请弹层/文件上传
├─ features/         功能 hooks（useAuth/useJobs/useNotifications/useAsync）
├─ domain/           领域层（纯函数，无 IO，可单测）
│  ├─ models.ts       VGA 领域模型（唯一真源）
│  ├─ jobStatus.ts    招聘状态机 / 能否申请判定
│  ├─ applicationStatus.ts  申请状态机
│  ├─ permissions.ts  权限判定
│  ├─ labels.ts       枚举→中文文案唯一真源
│  └─ validation.ts   表单/文件校验
├─ data/
│  ├─ ports.ts        Repository 端口（VGA 插座）
│  └─ mock/           MockRepository + 种子数据（信号发生器）
└─ stores/            Zustand（session / toast）
```

## 与后端对接（HDMI → VGA 转接头）

后端就绪后**只需新增一层 `data/http/`**，UI 与领域层一行不动：

1. 拿到后端接口文档，先写 `mappers.ts` 把后端 DTO 映射到 `domain/models.ts` 的类型。
2. 后端枚举值不同（如 `status: 1/2/3/4`）→ 在 mapper 里查表转换，不要把数字带进 UI。
3. 分页结构不同 → mapper 包成 `Page<T>`。
4. 上传方式不同（multipart / 预签名 URL / base64）→ 只改 `FileRepository.uploadResume` 实现。
5. 接口粒度不同（如「标记申请」拆成 3 个接口）→ 在 repository 实现内部分发。
6. 改 `.env`：`VITE_USE_MOCK=false`，`VITE_API_BASE` 指向后端；`vite.config.ts` 已预留 `/api` 代理。

**唯一允许「丑陋」的地方就是 mapper 层**：字段改名、兜底默认值、`if/else` 都合理；但后端 DTO 类型绝不泄漏到 `domain/` 之外。

## 关键业务规则（已在 domain 层 + mock 层双重落地）

- 简历仅 PDF / DOC / DOCX，单文件 ≤ 10 MB。
- 申请 4 态：处理中 / 已接受 / 已拒绝 / 已撤回，后三者终态不可变更。
- 发布者标记 3 种：确认 → 已接受、暂留 → 处理中、拒绝 → 已拒绝。
- 满员瞬间：招聘自动「已满员」，其余处理中申请自动「已拒绝」。
- 学生仅可发布竞赛组队、教师仅可发布校内活动；不可申请本人招聘；不可重复申请。
- 管理员入口与普通入口视觉/位置分离；治理删除须填原因 + 写审计日志。
