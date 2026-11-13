# 「济遇」校内招聘平台 · 前端开发执行计划（EXEC PLAN）

> 版本 v1.0 ｜ 日期 2026-10-25 ｜ 范围：**仅 Web 前端**（后端未就绪，本阶段以 Mock 驱动）
> 输入：《软件需求规格说明 V1.0（2026.10.18）》《UI界面.pdf》

---

## 0. 核心思路（一句话）

把前端当成一台**显示器**来做：先定义一块稳定的数据接口（**VGA**），用 Mock 信号把屏幕点亮；等后端（**HDMI**）到位，只加一层**转接头**把 HDMI 转成 VGA。

```
        ┌──────────────────────────────────────────────┐
        │  UI 组件 / 页面（只认 VGA 领域模型）             │
        └───────────────────┬──────────────────────────┘
                            │  调用
        ┌───────────────────▼──────────────────────────┐
        │  领域服务层：权限判定 · 状态机 · 表单规则 · 校验  │
        └───────────────────┬──────────────────────────┘
                            │  Repository 端口（interface）
        ┌───────────────────▼──────────────────────────┐
        │  MockRepository          HttpRepository       │
        │  （VGA 信号发生器）        （HDMI → Adapter）   │
        └──────────────────────────────────────────────┘
```

**收益**：后端改字段名、改枚举值、改分页结构、改上传方式（multipart / 预签名 URL / base64），UI 层一行不动。

**验收方式**：把 `MockRepository` 换成 `HttpRepository`，页面行为、校验提示、状态流转全部不变，即视为转接成功。

---

## 1. 需求理解

### 1.1 产品定位与边界

面向同济大学校内师生的 Web 端**竞赛组队 / 校内活动招聘**平台。自含型网页应用，强依赖学校统一身份认证。

**明确不做**（写进代码注释与验收清单，防止需求蔓延）：

- 校外企业招聘、在线签约、薪酬支付
- 移动原生 App（仅 Web，响应式适配移动浏览器）
- 在线简历编辑器、技能标签、结构化字段录入
- 独立注册入口、账号密码登录、找回密码
- 管理员的「编辑他人正文」能力（只能删 + 通知发布者自改）

### 1.2 角色与权限矩阵

> 权限 = **基础身份**（学生/教师）× **是否管理员**。管理员权限是「附加能力」，不改变基础身份，界面上必须与基础身份入口**视觉与位置分离**（SRS 2.3 硬性要求）。

| 能力 | 游客 | 学生 | 教师 | 管理员（附加） |
|---|---|---|---|---|
| 浏览招聘列表 / 详情 | ✅ | ✅ | ✅ | ✅ |
| 申请招聘（上传简历） | — | ✅（非本人发布） | — | ✅（沿用基础身份） |
| 撤回本人申请 | — | ✅ | — | ✅ |
| 发布招聘 | — | 竞赛组队 | 校内活动 | 按其基础身份 |
| 编辑 / 关闭 / 删除**本人**招聘 | — | ✅ | ✅ | ✅ |
| 查看本人招聘的申请列表 | — | ✅ | ✅ | ✅ |
| 标记申请（确认 / 暂留 / 拒绝） | — | ✅（本人招聘） | ✅（本人招聘） | ✅（本人招聘） |
| 删除**他人**不合规内容 | — | — | — | ✅（须填原因 + 写审计日志） |
| 编辑他人正文 | — | — | — | ❌ |
| 查看审计日志 | — | — | — | ✅ |

**推论（前端必须落实）**：

1. 招聘类型与身份绑定：学生发布页的类型字段锁定「竞赛组队」，教师锁定「校内活动」。
2. 详情页「编辑 / 关闭 / 删除」按钮的出现条件是 `招聘.发布者ID === 当前用户ID`，而不是「是学生/教师」。
3. 管理员在他人招聘详情页看到的是**独立的治理操作区**（红色描边、位于页面底部独立区块、文案「内容治理」），而不是混进常规操作按钮里。

### 1.3 功能域 → 页面映射

| 需求域 | 内容 | 主要页面 |
|---|---|---|
| F1 身份与准入 | 统一身份认证、身份判定、管理员判定、会话 | 登录页、全局路由守卫 |
| F2 浏览与筛选 | 列表、详情、类型筛选、时间排序、关键词 | 招聘广场、招聘详情 |
| F3 简历上传 | 申请时上传、格式与大小校验、补充说明 | 申请弹层 |
| F4 招聘发布与管理 | 发布、编辑、关闭、删除、申请列表、申请标记 | 发布页、我发布的、收到的申请 |
| F5 申请提交与处理 | 提交、撤回、确认 / 暂留 / 拒绝 | 申请弹层、我的申请、收到的申请 |
| F6 管理员治理 | 全平台查看、删除不合规内容、审计日志 | 管理后台 |
| F8 通知 | 站内通知、状态变更提醒 | 通知中心（铃铛 + 抽屉） |

### 1.4 关键业务规则（从 SRS 提炼，全部要在前端拦截 + 提示）

| 编号 | 规则 | 来源 |
|---|---|---|
| R1 | 简历仅 PDF / DOC / DOCX，单文件 ≤ 10 MB | FR-04 |
| R2 | 申请状态 4 态：处理中 / 已接受 / 已拒绝 / 已撤回；后三者为**终态，不可再变更** | 1.3 定义 |
| R3 | 发布者标记 3 种：确认→已接受、暂留→仍为处理中、拒绝→已拒绝 | 1.3 定义 |
| R4 | 已接受人数**不得超过**计划招募人数；已满员时「确认」按钮禁用并提示 | FR-06 |
| R5 | 满员瞬间：招聘状态自动变「已满员」，其余处理中申请**自动置为已拒绝** | FR-06 |
| R6 | 关闭后不再接受新申请，已有申请的处理不受影响 | FR-05 |
| R7 | 不可对本人发布的招聘提交申请 | FR-06 |
| R8 | 不可重复申请同一招聘 | FR-06 |
| R9 | 撤回后，简历文件与补充说明不再对发布者展示 | FR-04 |
| R10 | 删除招聘时若存在处理中/已接受申请，二次确认须说明**受影响范围**（N 条处理中 / M 条已接受） | FR-05、3.2 |
| R11 | 所有删除为不可逆操作，必须有二次确认 | 3.2 |
| R12 | 列表默认按发布时间倒序，**已关闭项排在最后** | FR-03 |
| R13 | 统一身份认证超时 5 s；服务不可用固定文案「统一身份认证服务暂时不可用，请稍后重试」，**不降级为本地密码登录** | 3.2 |
| R14 | 新学生从登录到完成首次申请 ≤ 5 步（不含认证页） | 3.4 |

---

## 2. UI 设计还原

### 2.1 页面清单（对应《UI界面.pdf》6 张设计稿）

> ⚠️ **本节为待校准推断**：《UI界面.pdf》的文本层为空，6 页均为整幅位图截图，尚未完成逐页视觉识别。下表是根据 SRS 功能域推出的**路由骨架**，稿件→路由的确切对应关系需在 M0 期间与设计稿逐页比对后确认（可能合并或拆分）。

设计稿共 6 页，覆盖主流程。落地时按下表建立路由，页面内组件按稿件的栅格、间距、字号实现。

| 稿件 | 页面 | 路由 |
|---|---|---|
| P1 | 登录 / 统一身份认证入口 | `/login` |
| P2 | 招聘广场（列表 + 筛选） | `/` |
| P3 | 招聘详情 | `/jobs/:id` |
| P4 | 发布 / 编辑招聘 | `/jobs/new`、`/jobs/:id/edit` |
| P5 | 个人主页（我的申请 / 我发布的） | `/me` |
| P6 | 申请处理 / 管理后台 | `/jobs/:id/applications`、`/admin` |

### 2.2 设计系统落地方式

**不写死颜色，全部走 token。** 在 `src/styles/tokens.css` 中用 CSS 变量声明设计系统，Tailwind 配置只引用变量，这样后续设计微调只改一处：

```css
:root {
  /* 品牌色 */
  --color-primary:        #0057B8;   /* 同济蓝，按设计稿取色校准 */
  --color-primary-hover:  #004a9c;
  --color-primary-soft:   #E8F0FB;   /* 标签底、选中态 */

  /* 语义色 */
  --color-success: #1F9D55;   /* 已接受 / 招募中 */
  --color-warning: #D9822B;   /* 处理中 / 暂留 */
  --color-danger:  #D93F3F;   /* 已拒绝 / 删除 / 治理操作 */
  --color-muted:   #8A94A6;   /* 已关闭 / 已撤回 */

  /* 中性色 */
  --color-bg:      #F5F7FA;
  --color-surface: #FFFFFF;
  --color-border:  #E5E8EE;
  --color-text:    #1B2333;
  --color-text-2:  #5A6478;

  /* 间距 4px 基准 */
  --space-1: 4px; --space-2: 8px;  --space-3: 12px; --space-4: 16px;
  --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-10: 40px;

  /* 圆角 / 阴影 */
  --radius-sm: 6px; --radius-md: 10px; --radius-lg: 16px; --radius-pill: 999px;
  --shadow-card: 0 1px 3px rgba(27,35,51,.06), 0 8px 24px rgba(27,35,51,.06);

  /* 字体 */
  --font-sans: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif;
}
```

> **上面这组色值是占位基线，不是从稿件取到的。** 对 6 张 PNG 做过像素采样（`_tools/palette3.py`），观察结果与上面的假设有出入，M0 必须校准：
>
> - 高饱和像素占比极低（0.3%–1.6%），且集中在**浅蓝**区间：`#A1CCF9`、`#C9E5FD`、`#88CBFF`。**没有检出接近 `#0057B8` 的深蓝大面积色块**，说明主色可能比预想的浅，或主色仅用于小面积按钮。
> - 大面积底色是 `#E4F0FC`~`#F1F6FC` 一类的极浅蓝灰，而非中性灰 `#F5F7FA`。
> - 页面上/下边缘有整条纯黑带（`#000000`），推断 6 页是**带外框的手机/浏览器截图**，内容区实际从 y≈156 开始。稿件是否包含状态栏、是否存在渐变，**目前未经验证**，实现前不得据此下结论。
>
> 因此第 4 步 M0 的第一件事是：把 6 页稿件按内容区裁切、放大，逐页确认主色、底色、字阶与栅格，再把 `tokens.css` 定稿。在此之前 UI 一律引用变量，禁止写死色值。

### 2.3 组件清单（按稿件反推）

| 组件 | 说明 |
|---|---|
| `AppHeader` | 左侧 Logo「济遇」+ 主导航；右侧：发布按钮、通知铃铛、头像下拉 |
| `UserMenu` | 姓名、学号/工号、身份标签、「个人主页」、「退出登录」 |
| `AdminEntry` | **仅在管理员可见**，独立红色入口，放在用户菜单**之外**的固定位置 |
| `JobCard` | 类型标签、标题、摘要、发布者、人数进度、状态徽章、发布时间 |
| `JobFilterBar` | 类型 Tab（全部 / 竞赛组队 / 校内活动）+ 关键词搜索 + 排序 |
| `StatusBadge` | 招聘 3 态 + 申请 4 态统一徽章，颜色映射见 2.2 语义色 |
| `QuotaProgress` | 「已接受 2 / 计划 3」进度条，满员变绿 |
| `ApplicationCard` | 申请者信息、简历文件、补充说明、状态、操作按钮组 |
| `FileUploader` | 拖拽 + 点击上传，前端即时校验格式/大小，展示文件名与体积 |
| `ConfirmDialog` | 通用二次确认，支持「影响范围」插槽（R10） |
| `ReasonDialog` | 管理员删除原因必填（≥10 字） |
| `NotificationDrawer` | 站内通知列表，未读红点 |
| `EmptyState` | 空列表占位（无招聘 / 无申请 / 无通知） |
| `Pagination` | 列表分页，移动端切换为「加载更多」 |

---

## 3. 技术选型与工程架构

### 3.1 技术栈

| 层次 | 选择 | 理由 |
|---|---|---|
| 框架 | **React 18 + TypeScript 5** | 生态成熟，类型系统是「VGA 契约」的载体 |
| 构建 | **Vite** | 冷启动快，适合演示与迭代 |
| 路由 | **React Router 6** | 嵌套路由 + 路由守卫 |
| 样式 | **Tailwind CSS + CSS 变量 token** | 快速还原设计稿，同时保留设计系统单一真源 |
| 状态 | **Zustand**（会话/全局）+ **TanStack Query**（服务端状态） | 避免 Redux 样板代码；Query 天然处理 loading/error/缓存 |
| 表单 | **React Hook Form + Zod** | Zod schema 同时承担「校验规则」与「VGA 类型来源」 |
| 图标 | **lucide-react** | 线性图标，与设计稿风格一致 |
| 测试 | **Vitest + React Testing Library + MSW** | 状态机与权限路径必须有单测（SRS 3.4 可测试性） |
| 代码规范 | ESLint + Prettier + `tsc --noEmit` | CI 三道闸 |

### 3.2 分层架构（强制约束）

```
src/
├─ pages/            ① 页面层：只做编排，不含业务规则
├─ components/       ② 展示组件：纯 props，不含数据获取
├─ features/         ③ 功能模块：hooks + 表单 + 局部状态
├─ domain/           ④ 领域层：★纯函数，无 IO，可单测
│   ├─ models.ts        VGA 领域模型（唯一真源）
│   ├─ permissions.ts   权限判定
│   ├─ jobStatus.ts     招聘状态机
│   ├─ applicationStatus.ts  申请状态机
│   └─ validation.ts    校验规则（Zod schema）
├─ data/
│   ├─ ports.ts         Repository 接口（VGA 插座）
│   ├─ mock/            MockRepository + 种子数据（信号发生器）
│   └─ http/            HttpRepository + DTO 映射（转接头）
├─ styles/tokens.css
└─ main.tsx
```

**铁律**：

1. `pages/` 与 `components/` **禁止** `import` 任何 `data/http/*`，只能 `import` `data/ports.ts` 的接口 + 通过 DI 拿到实例。
2. `domain/` **禁止** 出现 `fetch`、`axios`、`window`、`localStorage`。
3. 所有接口返回的原始 JSON **不得**直接进入组件，必须先经 mapper 转成 `domain/models.ts` 的类型。

### 3.3 依赖注入（换接口的唯一开关）

```ts
// src/data/index.ts
export const repo: Repositories = import.meta.env.VITE_USE_MOCK === 'true'
  ? createMockRepository()
  : createHttpRepository({ baseUrl: import.meta.env.VITE_API_BASE });
```

演示阶段 `VITE_USE_MOCK=true`；后端就绪后改 `.env` 一行即可切换，代码零改动。

---

## 4. 数据契约（VGA 接口）

### 4.1 领域模型 `domain/models.ts`

```ts
export type UserRole = 'student' | 'teacher';

export interface User {
  id: string;              // 学号 / 工号
  name: string;
  email: string;
  role: UserRole;
  isAdmin: boolean;        // 附加权限，与 role 正交
  avatarUrl?: string;
}

export type JobType = 'competition' | 'campus_activity';
/** 招募中 / 已满员 / 已关闭 */
export type JobStatus = 'open' | 'full' | 'closed';

export interface Job {
  id: string;
  type: JobType;
  title: string;              // 竞赛名称 / 活动名称
  description: string;        // 需求描述
  requirement: string;        // 用人要求（补充说明）
  recruitCount: number;       // 计划招募人数
  acceptedCount: number;      // 已接受人数（≤ recruitCount）
  deadline: string;           // ISO8601 截止时间
  status: JobStatus;
  publisher: Pick<User, 'id' | 'name' | 'role'>;
  createdAt: string;
  updatedAt: string;
  /** 列表接口附带：当前用户在此招聘下的申请状态（用于列表标注） */
  myApplicationStatus?: ApplicationStatus | null;
  applicationCount: number;   // 收到的申请总数（发布者视角）
}

/** 处理中 / 已接受 / 已拒绝 / 已撤回；后三者终态 */
export type ApplicationStatus = 'pending' | 'accepted' | 'rejected' | 'withdrawn';

export interface ResumeFile {
  id: string;
  fileName: string;
  size: number;               // bytes
  mimeType: 'application/pdf' | 'application/msword'
          | 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  uploadedAt: string;
  /** 仅在「申请者本人」「该招聘发布者」「管理员治理场景」下由后端下发 */
  downloadUrl?: string;
}

export interface Application {
  id: string;
  jobId: string;
  jobTitle: string;
  jobType: JobType;
  applicant: Pick<User, 'id' | 'name' | 'role'>;
  resume: ResumeFile;
  note?: string;              // 补充说明（可选）
  status: ApplicationStatus;
  createdAt: string;
  updatedAt: string;
  /** 撤回后置 true，后端不再返回 resume.downloadUrl */
  resumeHidden: boolean;
}

export interface Notification {
  id: string;
  type: 'application_accepted' | 'application_rejected' | 'application_withdrawn'
      | 'job_removed_by_admin' | 'job_closed';
  title: string;
  jobId: string;
  jobTitle: string;
  status: ApplicationStatus | JobStatus;
  createdAt: string;
  read: boolean;
}

export interface AuditLog {
  id: string;
  operatorId: string;
  operatorName: string;
  operatorRole: UserRole;
  targetType: 'job' | 'application' | 'resume';
  targetId: string;
  targetTitle: string;
  action: 'delete_job' | 'delete_application' | 'view_resume' | 'delete_own_job';
  reason?: string;
  createdAt: string;
}

/** 统一分页信封：后端换成分页结构时只改 mapper */
export interface Page<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export interface JobQuery {
  type?: JobType | 'all';
  keyword?: string;
  page: number;
  pageSize: number;
}
```

### 4.2 Repository 端口 `data/ports.ts`

```ts
export interface AuthRepository {
  /** 跳转统一身份认证，返回会话用户；超时 5s 抛 AuthUnavailableError */
  login(): Promise<User>;
  logout(): Promise<void>;
  getCurrentUser(): Promise<User | null>;
}

export interface JobRepository {
  list(q: JobQuery): Promise<Page<Job>>;
  detail(id: string): Promise<Job>;
  create(input: CreateJobInput): Promise<Job>;
  update(id: string, input: UpdateJobInput): Promise<Job>;
  close(id: string): Promise<Job>;
  /** 删除；返回受影响申请数供确认弹窗展示（R10） */
  remove(id: string): Promise<{ affectedPending: number; affectedAccepted: number }>;
  listMine(q: JobQuery): Promise<Page<Job>>;
}

export interface ApplicationRepository {
  submit(input: SubmitApplicationInput): Promise<Application>;
  withdraw(applicationId: string): Promise<Application>;
  listMine(q: { page: number; pageSize: number }): Promise<Page<Application>>;
  listForJob(jobId: string, q: { page: number; pageSize: number }): Promise<Page<Application>>;
  /** 发布者标记：accept / hold / reject */
  mark(applicationId: string, action: 'accept' | 'hold' | 'reject'): Promise<Application>;
}

export interface NotificationRepository {
  list(q: { page: number; pageSize: number }): Promise<Page<Notification>>;
  markRead(id: string): Promise<void>;
  unreadCount(): Promise<number>;
}

export interface AdminRepository {
  listAllJobs(q: JobQuery): Promise<Page<Job>>;
  /** 治理删除：必须带原因，写审计日志，通知发布者 */
  removeJobWithReason(jobId: string, reason: string): Promise<void>;
  listAuditLogs(q: { page: number; pageSize: number }): Promise<Page<AuditLog>>;
}

export interface FileRepository {
  /** 前端已校验格式/大小，此处只负责上传，返回 ResumeFile */
  uploadResume(file: File, onProgress?: (p: number) => void): Promise<ResumeFile>;
}

export interface Repositories {
  auth: AuthRepository;
  jobs: JobRepository;
  applications: ApplicationRepository;
  notifications: NotificationRepository;
  admin: AdminRepository;
  files: FileRepository;
}
```

### 4.3 Mock 实现要点

- 内存数据库 + `localStorage` 持久化，刷新不丢数据（便于演示）。
- 种子数据：**12 条招聘**（8 条竞赛组队 / 4 条校内活动，含 1 条已满员、1 条已关闭、1 条已过期）、**6 个用户**（3 学生 / 2 教师 / 1 管理员学生）、**20 条申请**（覆盖全部 4 种状态）。
- 内置 **300~600 ms 随机延迟**，强制前端把 loading / 空态 / 骨架屏写对（避免演示时闪屏）。
- Mock 必须**复刻真实业务规则**：满员自动拒绝、重复申请拦截、本人不可申请、终态不可变更。这样前端的状态机才能被真实地测出来。
- 提供 `window.__mock.reset()` / `window.__mock.seed('scenario')` 便于演示时切换场景。

### 4.4 与后端对接的转接层（HDMI → VGA）

后端到位后，新增 `data/http/`，每个 Repository 一个实现 + 一个 mapper：

```
data/http/
├─ httpClient.ts        // axios 实例、401 拦截、CSRF、错误码归一
├─ mappers.ts           // DTO → Domain（唯一允许接触后端字段名的地方）
├─ jobApi.ts
├─ applicationApi.ts
└─ authApi.ts
```

**对接流程（写进 README，避免以后扯皮）**：

1. 拿到后端接口文档，先只改 `mappers.ts`，把后端字段/枚举映射到 `domain/models.ts`。
2. 若后端枚举值不同（如 `status: 1/2/3/4`），在 mapper 里查表转换，**不要把数字带进 UI**。
3. 若后端分页结构不同（`{data, total, page}` vs `{records, count}`），在 mapper 里包成 `Page<T>`。
4. 若后端上传走预签名 URL，改 `FileRepository.uploadResume` 实现，UI 不动。
5. 若后端接口粒度不同（如「标记申请」拆成 3 个接口），在 `applicationApi.ts` 内部分发。
6. 切 `.env` 的 `VITE_USE_MOCK=false`，跑一遍第 8 章的验收清单。

**这一层是唯一允许「丑陋」的地方**，mapper 里写 `if/else` 兜底、默认值、字段改名都合理；但绝不允许把后端 DTO 类型泄漏到 `domain/` 之外。

---

## 5. 核心逻辑设计

### 5.1 申请状态机 `domain/applicationStatus.ts`

```
                    ┌──────────────┐
     提交申请 ─────▶ │   pending    │ ◀── 暂留（hold）
                    │   处理中      │
                    └──┬───┬───┬───┘
          确认(accept) │   │   │ 撤回(withdraw, 仅申请人)
                       │   │   └──────────────▶ ┌────────────┐
                       │   │  拒绝(reject)       │ withdrawn  │ 终态
                       │   └──────────────────▶ └────────────┘
                       ▼                        ┌────────────┐
                 ┌───────────┐   满员自动        │ rejected   │ 终态
                 │ accepted  │ ───────────────▶ └────────────┘
                 │ 已接受     │  （其余 pending）
                 └───────────┘ 终态
```

```ts
const TERMINAL: ApplicationStatus[] = ['accepted', 'rejected', 'withdrawn'];

export const isTerminal = (s: ApplicationStatus) => TERMINAL.includes(s);

export const canWithdraw = (s: ApplicationStatus) => s === 'pending';
export const canMark = (s: ApplicationStatus) => s === 'pending';

/** 纯函数：返回新状态或抛领域错误，便于单测 */
export function transition(
  current: ApplicationStatus,
  action: 'accept' | 'hold' | 'reject' | 'withdraw'
): ApplicationStatus {
  if (isTerminal(current)) throw new DomainError('该申请已进入终态，不可再变更');
  switch (action) {
    case 'accept':   return 'accepted';
    case 'reject':   return 'rejected';
    case 'hold':     return 'pending';
    case 'withdraw': return 'withdrawn';
  }
}
```

### 5.2 招聘状态机 `domain/jobStatus.ts`

```
open ──(acceptedCount === recruitCount)──▶ full
  │                                          │
  └──(发布者手动关闭 / 到期)──▶ closed ◀──────┘
```

- `canApply(job, user)` 统一判定：`status === 'open'` && 未过 `deadline` && `user.role === 'student'` && `job.publisher.id !== user.id` && `myApplicationStatus == null`。
- 判定结果同时驱动**按钮可用性**与**tooltip 原因文案**，两者共用同一个函数，避免「按钮能点但提交报错」。

### 5.3 权限守卫

三层，缺一不可：

| 层 | 实现 | 作用 |
|---|---|---|
| 路由层 | `<RequireAuth>` / `<RequireRole roles>` / `<RequireOwner>` | 未登录跳认证；无权限跳 403 页 |
| 组件层 | `usePermission()` 返回布尔，控制按钮渲染 | 不渲染而不是禁用（避免「能点但报错」） |
| 提交层 | 领域函数二次校验 | 防绕过；Mock/Http 层也校验一次 |

```ts
export const can = {
  editJob:    (u: User, job: Job) => u.id === job.publisher.id,
  deleteJob:  (u: User, job: Job) => u.id === job.publisher.id,
  moderateJob:(u: User, job: Job) => u.isAdmin && u.id !== job.publisher.id,
  applyJob:   (u: User, job: Job) => canApply(job, u).ok,
  manageApps: (u: User, job: Job) => u.id === job.publisher.id,
  viewResume: (u: User, app: Application, job: Job) =>
      u.id === app.applicant.id || u.id === job.publisher.id
      || (u.isAdmin && !app.resumeHidden),
};
```

### 5.4 表单校验（Zod schema，同时是类型来源）

```ts
export const createJobSchema = z.object({
  type: z.enum(['competition', 'campus_activity']),
  title: z.string().trim().min(2, '请输入名称').max(60, '不超过 60 字'),
  description: z.string().trim().min(10, '请描述需求，至少 10 字').max(2000),
  requirement: z.string().trim().max(1000).optional(),
  recruitCount: z.coerce.number().int('须为整数')
      .min(1, '计划招募人数至少为 1').max(50, '不超过 50 人'),
  deadline: z.string().refine(v => new Date(v) > new Date(), '截止时间须晚于当前时间'),
});

export const resumeSchema = z.object({
  file: z.instanceof(File)
    .refine(f => ACCEPTED_EXT.includes(ext(f.name)), '仅支持 PDF / DOC / DOCX 格式')
    .refine(f => f.size <= 10 * 1024 * 1024, '文件不得超过 10 MB'),
  note: z.string().trim().max(500, '补充说明不超过 500 字').optional(),
});
```

**校验时机**：字段失焦 + 提交前全量；上传文件**选择瞬间**即校验（不等提交），错误就地展示（SRS 3.4 易用性）。

### 5.5 文件上传

1. `<input accept=".pdf,.doc,.docx">` 仅作提示，真正校验走 `resumeSchema`（用户可拖入任意文件）。
2. 前端校验通过 → 调 `files.uploadResume` → 拿 `ResumeFile` → 随 `applications.submit` 一并提交。
3. **失败不产生残缺申请**：上传失败即中断，不调用提交接口（R1 配套约束）。
4. 展示文件名 + 体积 + 移除按钮；上传中显示进度条。

---

## 6. 路由与页面职责

| 路由 | 页面 | 守卫 | 关键交互 |
|---|---|---|---|
| `/login` | 登录 | 游客 | 唯一入口，无注册链接（R13 文案） |
| `/` | 招聘广场 | 无需登录可浏览 | 类型 Tab、搜索（防抖 300ms）、分页；已申请项标注状态 |
| `/jobs/:id` | 招聘详情 | 浏览公开 | 申请入口 / 发布者管理区 / 管理员治理区（三块互斥） |
| `/jobs/new` | 发布 | 登录 | 类型锁定；提交成功跳详情 |
| `/jobs/:id/edit` | 编辑 | 发布者 | 关闭招聘按钮在此页 |
| `/jobs/:id/applications` | 收到的申请 | 发布者 | 简历预览、确认/暂留/拒绝、满员禁用 |
| `/me` | 个人主页 | 登录 | Tab：我的申请 / 我发布的 |
| `/me/applications` | 我的申请 | 学生 | 撤回（仅 pending） |
| `/admin` | 管理后台 | 管理员 | 全平台列表 + 治理删除 + 审计日志 |
| `/403`、`/404` | 异常页 | — | 明确文案 + 返回首页 |

**跨页面一致性**：所有「状态徽章」共用 `StatusBadge`；所有「人数」共用 `QuotaProgress`；所有「删除」共用 `ConfirmDialog`。

---

## 7. 里程碑与排期

| 阶段 | 交付物 | 预估 | 验收标志 |
|---|---|---|---|
| **M0 基建** | Vite + TS + Tailwind + 路由骨架 + tokens + 布局壳 | 1.5 天 | 空页面能跑起来，token 生效 |
| **M1 契约** | `domain/models.ts`、`ports.ts`、Zod schema、状态机纯函数 + 单测 | 1.5 天 | 单测覆盖率 ≥ 90%（domain 层） |
| **M2 Mock** | MockRepository + 种子数据 + 场景切换 | 1.5 天 | 所有端口方法可调用，业务规则已复刻 |
| **M3 认证** | 登录页、会话、路由守卫、403 页 | 1 天 | 未登录访问受限页正确跳转 |
| **M4 浏览** | 广场列表、筛选、搜索、分页、详情 | 2 天 | 与 P2/P3 稿件像素对齐 |
| **M5 发布管理** | 发布/编辑/关闭/删除 + 二次确认（含影响范围） | 2 天 | P4/P5 对齐；R10、R11 通过 |
| **M6 申请流程** | 申请弹层、上传、我的申请、撤回 | 2 天 | R1、R7、R8、R9 通过 |
| **M7 处理流程** | 收到申请、确认/暂留/拒绝、满员联动 | 2 天 | R4、R5、R6 通过 |
| **M8 管理员** | 治理删除（填原因）、审计日志 | 1.5 天 | R11 + 审计字段完整 |
| **M9 通知** | 站内通知、未读数、抽屉 | 1 天 | FR-08 前端部分 |
| **M10 打磨** | 响应式（≤768px）、空态、骨架屏、错误兜底、无障碍 | 2 天 | 移动端可用；键盘可操作 |
| **M11 验收** | 全量回归 + 演示数据 + README | 1 天 | 第 8 章清单全绿 |

**合计约 18 人日。** 可按「M0–M4 先跑通一条主线」做第一次演示，再并行 M5/M6/M7。

---

## 8. 验收清单（对齐 SRS 第 5 章 TC-01 ~ TC-13）

| 用例 | 前端验收点 |
|---|---|
| TC-01 登录 | 无注册入口；登录后首页默认展示招聘；个人主页可见两个入口 |
| TC-02 他人信息不可编辑 | 他人详情页无编辑/删除按钮；手改 URL 进 `/edit` 被守卫拦截并提示 |
| TC-03 本人可编辑删除 | 编辑生效；删除弹二次确认，确认后列表消失 |
| TC-04 管理员可删他人内容 | 治理区可见；未填原因不能提交；提交后出现审计记录与通知 |
| TC-05 按类型筛选 | 选「竞赛组队」后列表仅剩该类，且每条带类型标签 |
| TC-06 发布必填校验 | 名称留空 / 人数填 0 → 拒绝并定位到出错字段；列表不新增 |
| TC-07 格式与大小校验 | `.txt` 与 >10MB PDF 均在**选择瞬间**报错，不产生申请记录 |
| TC-08 正常上传 | 2MB PDF + 补充说明 → 申请创建成功，状态「处理中」 |
| TC-09 撤回后文件不可见 | 撤回后状态「已撤回」；发布者侧简历与说明消失 |
| TC-10 满员自动拒绝其余 | 计划 1 人、A/B 申请；确认 A → A 已接受、招聘已满员、B 自动已拒绝、双方各有通知 |
| TC-11 满员后确认被阻止 | 「确认」按钮禁用 + tooltip「已满员」；状态不变 |
| TC-12 暂留后仍处理中 | 暂留后徽章仍为「处理中」；再确认成功 |
| TC-13 状态变更触发通知 | 拒绝后申请者通知中心出现条目，含类型、招聘名、状态、跳转链接 |

**额外自检项**：

- [ ] 断网 / Mock 抛错时，页面展示可重试的错误态，不白屏
- [ ] 375px 宽度下列表、详情、申请弹层均可用，无横向滚动
- [ ] 所有删除、撤回、确认操作有明确反馈（Toast + 状态更新）
- [ ] 刷新后登录态与 Mock 数据不丢
- [ ] `tsc --noEmit`、ESLint、单测三绿

---

## 9. 风险与待确认

| # | 风险 / 待确认 | 应对 |
|---|---|---|
| 1 | 统一身份认证接口未申请到 | 前端按「跳转 + 回调」建模，Mock 用「选择用户登录」模拟；若最终改用邮箱验证，只替换 `AuthRepository` |
| 2 | 设计稿未覆盖的页面（通知中心、审计日志、403/404） | 沿用 tokens 与组件语言自绘，先给评审再实现 |
| 3 | 后端分页 / 枚举 / 上传方式未知 | 已在 4.4 定义转接流程，mapper 层兜底 |
| 4 | 管理员入口与普通入口的分离方式 | 采用「用户菜单外独立入口 + 独立路由 `/admin` + 详情页独立治理区块」三重分离 |
| 5 | 满员自动拒绝的时序在前端如何呈现 | Mock 与后端均以服务端结果为准；前端在标记成功后**重新拉取**申请列表，不本地推断（避免与后端不一致） |
| 6 | 简历文件的临时可见性 | 前端不缓存 downloadUrl；撤回后立即失效本地引用 |
| 7 | 演示环境是否需要「一键切换角色」 | 建议 Mock 模式提供调试面板（仅 dev 构建），便于答辩演示不同身份 |

---

## 10. 交付物

1. 可运行前端工程（`npm i && npm run dev`）
2. `EXEC_PLAN.md`（本文档）
3. `README.md`：启动方式、Mock 场景说明、**后端对接改造指南**（4.4 的展开）
4. Mock 种子数据与场景脚本
5. 领域层单测（状态机、权限、校验）
6. 演示脚本（3 分钟走完：登录 → 浏览 → 申请 → 切换发布者 → 处理 → 满员 → 管理员治理）

