# JiMeet 后端接口契约

契约基线：Sprint1 阶段 1｜更新日期：2026-10-26
本文是前后端对接的唯一接口正文。路径相对服务地址，统一加 `/api/v1`，不带末尾斜杠；文件路径相对项目根目录。开发范围与分工遵循已核验的 Sprint1 计划，本文不代替阶段完成记录。

## 1. 接口状态与交付边界

- **已实现**：当前代码可调用；开发登录还要求开发开关同时开启。
- **待实现**：本阶段确定的目标契约，当前尚未注册路由，不能用于真实业务联调。对应阶段完成后再更新状态。
- **预留**：已注册占位路由，明确返回 501；不属于本次正式认证交付。

下表按“HTTP 方法 + 路径”标识接口；同一路径的不同方法分别验收。

| 方法 | 路径 | 状态 | 阶段 / 负责人 |
| --- | --- | --- | --- |
| GET | `/healthz` | 已实现 | 1 / czh 核验 |
| GET | `/auth/csrf` | 已实现 | 1 / czh 核验 |
| POST | `/auth/dev-login` | 已实现 | 1 / czh 核验 |
| POST | `/auth/logout` | 已实现 | 1 / czh 核验 |
| GET | `/me` | 已实现 | 1 / czh 核验 |
| PATCH | `/me` | 已实现 | 1 / czh 核验 |
| POST | `/me/privacy-consent` | 已实现 | 1 / czh 核验 |
| GET | `/auth/sso/login` | 预留 | 正式认证后续确定 |
| GET | `/auth/sso/callback` | 预留 | 正式认证后续确定 |
| GET | `/tags` | 待实现 | 2 / czh |
| GET | `/recruitments` | 待实现 | 2 / czh |
| POST | `/recruitments` | 待实现 | 2 / czh |
| GET | `/recruitments/{id}` | 待实现 | 2 / czh |
| PATCH | `/recruitments/{id}` | 待实现 | 2 / czh |
| DELETE | `/recruitments/{id}` | 待实现 | 2 / czh |
| POST | `/recruitments/{id}/close` | 待实现 | 2 / czh |
| GET | `/me/recruitments` | 待实现 | 2 / czh |
| POST | `/recruitments/{id}/applications` | 待实现 | 3 / czh |
| GET | `/recruitments/{id}/applications` | 待实现 | 3 / czh |
| GET | `/me/applications` | 待实现 | 3 / czh |
| GET | `/applications/{id}` | 待实现 | 3 / czh |
| GET | `/applications/{id}/resume` | 待实现 | 3 / czh |
| PATCH | `/applications/{id}` | 待实现 | 4 / zf |
| POST | `/applications/{id}/withdraw` | 待实现 | 4 / zf |
| POST | `/applications/{id}/accept` | 待实现 | 4 / zf |
| POST | `/applications/{id}/reject` | 待实现 | 4 / zf |
| POST | `/applications/{id}/hold` | 待实现 | 4 / zf |
| POST | `/applications/{id}/unhold` | 待实现 | 4 / zf |
| POST | `/applications/{id}/read` | 待实现 | 4 / zf，申请修改已阅确认 |
| GET | `/notifications` | 待实现 | 5 / zf |
| GET | `/notifications/unread-count` | 待实现 | 5 / zf |
| POST | `/notifications/{id}/read` | 待实现 | 5 / zf |
| POST | `/notifications/read-all` | 待实现 | 5 / zf |

阶段 6 负责回归和交付。`/applications/{id}/read` 是计划中“未读修改确认方式”的具体约定，不是通知已读接口；本轮不实现该路由。聊天、推荐、其他用户主页、完整注册/登录页面、回收站和真实邮件发送均不在本文的本次交付范围内。

### 1.1 现有代码基线

已存在 10 个业务模型及迁移、PostgreSQL 搜索索引、统一响应/错误码/分页、对象权限、招募状态工具、私有文件存储、通知创建与审计。当前总路由仅挂载 `core` 和 `accounts`；模型、工具函数和测试辅助流程不等于招募/申请 HTTP 接口已实现。

依赖以 `backend/requirements/base.txt` 为准：Python 3.12+、PostgreSQL 15+，Django 6.1.2、DRF 3.18.3、psycopg 3.3.6。配置从进程环境变量读取，不自动加载 `.env`；变量清单见 `backend/.env.example`。数据库、私有文件目录与凭据按各成员环境配置，个人部署过程不写入接口契约。

已有命令：`seed_tags`、`run_sync_recruitments`。`run_send_emails`、`run_purge_applications`、`run_cleanup_orphan_files`、`run_cleanup_audit_logs` 目前显式报 `CommandError: reserved`；不得把占位命令视为已完成任务。邮件 `dispatch` 仅记录日志。

## 2. 通用契约

### 2.1 请求、标识与时间

- 默认要求登录；仅健康检查、CSRF 获取、开发登录及 SSO 占位接口公开。学生和教师使用同一业务操作规则，管理员身份不增加申请内容、简历读取权限。
- JSON 请求使用 `Content-Type: application/json`；上传和替换简历使用 `multipart/form-data`。文件下载成功返回文件流。
- JSON 字段使用 `snake_case`。用户仅暴露 32 位十六进制 `uid`；招募、申请、通知、标签使用正整数 `id`。不输出用户数据库主键、`real_id`、认证标识、私有文件路径或邮箱等无关身份信息。
- 时间为带时区的 ISO 8601 字符串，例如 `2026-11-15T18:00:00+08:00`，客户端按时间点解析；不能依赖固定时区文本。截止边界以服务端时间为准。
- 下文“省略字段”与值为 `null` 不同：无权读取的字段省略；有权读取但没有值的字段返回 `null`。列表无结果返回空数组。
- 目标业务接口拒绝未声明、只读的请求字段；JSON 人数及 ID 接受整数，拒绝布尔值、浮点数和数字字符串。查询参数按声明解析；未知或重复查询键返回 400。请求路径中的不存在资源返回 404。

### 2.2 响应信封与分页

进入 API 视图的 JSON 响应统一为：

```json
{
  "code": "OK",
  "message": "",
  "data": {},
  "request_id": "0123456789abcdef0123456789abcdef"
}
```

成功时 `code=OK`、`message` 为空字符串；无返回数据时 `data=null`。失败时 `data=null`，有校验详情时为 `{"details": {...}}`。前端依据 HTTP 状态及 `code` 判断分支，`message` 用于展示，不以其中文内容编写判断逻辑。

客户端可传 `X-Request-Id`（1～64 位字母、数字、短横线）；缺失或无效则由服务端生成。响应头 `X-Request-Id` 与信封 `request_id` 一致。

分页接口接受 `page`、`page_size`，默认 1、20，最大每页 50；省略或空串使用默认值，非正整数或超限返回 400。越界页正常返回空列表，`total` 为权限过滤后的总数：

```json
{
  "code": "OK",
  "message": "",
  "data": {"items": [], "page": 1, "page_size": 20, "total": 0},
  "request_id": "0123456789abcdef0123456789abcdef"
}
```

**例外**：未命中路由的 404、Django 中间件或反向代理直接拒绝的请求可能不是 JSON；下载成功也不是信封。客户端先检查 HTTP 状态与 `Content-Type`，不能对所有响应直接调用 `json()`。开发登录开关关闭而未注册路由时适用此例外；已经注册但运行时开关关闭时，视图返回 JSON 404 `NOT_FOUND`。

### 2.3 错误码

| code | HTTP | 契约含义 |
| --- | --- | --- |
| OK | 200 / 201 | 读取/更新成功，或资源创建成功 |
| UNAUTHENTICATED | 401 | 未登录或会话失效 |
| AUTH_FAILED | 401 | 开发身份不合法、身份或邮箱冲突 |
| FORBIDDEN | 403 | 无权执行操作、CSRF 校验失败或账号停用 |
| NOT_FOUND | 404 | 资源不存在、已删除或对访问者不可见 |
| VALIDATION_ERROR | 400 | 字段、查询参数或 JSON 格式错误 |
| VALIDATION_ERROR | 415 | 请求使用了该接口不支持的媒体类型 |
| METHOD_NOT_ALLOWED | 405 | 路径存在，但不支持该方法 |
| PRIVACY_NOT_CONSENTED | 403 | 未确认个人信息处理告知，不能提交申请 |
| SELF_APPLICATION_FORBIDDEN | 403 | 不能申请本人发布的招募 |
| RECRUITMENT_NOT_OPEN | 409 | 当前不允许新投递 |
| RECRUITMENT_NOT_EDITABLE | 409 | 当前不允许编辑、关闭或按发布者身份删除 |
| RECRUITMENT_FULL | 409 | 已满员，不能再接受申请 |
| PROCESSING_WINDOW_CLOSED | 409 | 已关闭且到达七天处理边界 |
| HEADCOUNT_BELOW_ACCEPTED | 409 | 人数上限低于已接受人数 |
| DUPLICATE_APPLICATION | 409 | 对同一招募已有未撤回申请 |
| APPLICATION_NOT_PROCESSING | 409 | 申请已不是处理中，不能执行该状态操作 |
| INVALID_RESUME_FILE | 400 | 文件校验失败；`data.details.reason` 为 `type`、`size` 或 `signature` |
| INTERNAL_ERROR | 500 / 501 / 503 | 内部异常 / 已注册的功能占位 / 健康检查数据库不可用 |
| SSO_UNAVAILABLE | 503 | 正式 SSO 故障预留码，本阶段不使用 |

400 示例：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "参数校验失败",
  "data": {"details": {"max_headcount": "必须是 1 至 50 的整数"}},
  "request_id": "0123456789abcdef0123456789abcdef"
}
```

`details` 的字段值可能是字符串或字符串数组，前端需兼容。无权读取他人申请或通知时返回 404；对象可见但动作身份错误时返回 403。状态冲突才返回 409，不利用业务错误泄露不可见对象的状态。

## 3. 会话与前端开发联调

### 3.1 默认使用同源开发代理

前端统一请求相对路径 `/api/v1/...`，由前端开发服务器代理至配置的后端服务，不在页面中硬编码后端地址。代理保留路径、`Host`、`Origin` 和 Cookie，并原样转发 `Set-Cookie`；代理目标通过环境配置指定。

前端尚未建工程；以下仅为选用 Vite 时的配置参考，应合入前端自己的配置，不在本阶段新建前端项目：

```javascript
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  if (!env.DEV_API_TARGET) {
    throw new Error('请配置 DEV_API_TARGET 为后端服务的 origin');
  }
  return {
    server: {
      strictPort: true,
      proxy: {
        '/api/v1': {
          target: env.DEV_API_TARGET,
          changeOrigin: false,
        },
      },
    },
  };
});
```

`DEV_API_TARGET` 只供开发服务器使用，不是浏览器请求前缀。浏览器通过同一前端 origin 完成全部调用；本机开发固定使用同一种主机名，不在 `localhost` 和 IP 地址之间切换会话。现有开发配置允许本机主机名，其他部署主机另行配置。

保留 Host 后，浏览器 Origin 与 Django 看到的请求 origin 一致，通常无需 `CSRF_TRUSTED_ORIGINS`。若代理必须改写 Host，则后端应仅将实际前端 origin（含协议与端口）加入该环境变量；重启后端使配置生效。**仅配置 CSRF 信任来源不等于启用 CORS**。本次采用同源代理，不引入跨域中间件、不关闭 CSRF；正式部署的 HTTPS 与代理配置届时另行核验。

参考：[Vite 开发代理](https://vite.dev/config/server-options#server-proxy)、[Django CSRF 来源校验](https://docs.djangoproject.com/en/6.1/ref/csrf/)。

### 3.2 Session、CSRF 与隐私确认顺序

1. `GET /auth/csrf` 获取 `data.csrf_token` 并接收 `csrftoken` Cookie。
2. `POST /auth/dev-login` 携带 Cookie、JSON 身份和 `X-CSRFToken`。
3. 登录成功会建立 `sessionid` 并轮换 CSRF 密钥；再次 `GET /auth/csrf` 更新前端持有的令牌。
4. `GET /me` 读取本人身份及 `privacy_consented`。**只有用户明确确认告知后**才调用 `POST /me/privacy-consent`；登录不等于同意，不能自动确认。
5. 后续 POST/PATCH/DELETE 携带当前 CSRF 令牌。退出后丢弃前端缓存的本人资料；再次登录重新走上述流程。

`sessionid` 为 HttpOnly Cookie，前端不读取、不复制到请求体或本地存储；`fetch` 使用 `credentials: 'same-origin'`。接口返回的 masked CSRF token 和当前 `csrftoken` Cookie 值均可用于请求头，但登录前的旧令牌不可继续使用。实际规则见 [Django CSRF 文档](https://docs.djangoproject.com/en/6.1/ref/csrf/)。

浏览器调用示例（此处只调用已实现接口）：

```javascript
const API_BASE = '/api/v1';
let csrfToken;

async function api(path, { method = 'GET', json } = {}) {
  const headers = { Accept: 'application/json' };
  if (json !== undefined) headers['Content-Type'] = 'application/json';
  if (['POST', 'PATCH', 'DELETE'].includes(method)) {
    headers['X-CSRFToken'] = csrfToken;
  }
  const response = await fetch(`${API_BASE}${path}`, {
    method, headers, credentials: 'same-origin',
    body: json === undefined ? undefined : JSON.stringify(json),
  });
  if (!response.headers.get('Content-Type')?.includes('application/json')) {
    throw new Error(`非 JSON 响应：HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (!response.ok || payload.code !== 'OK') {
    throw new Error(`${payload.code}: ${payload.message} (${payload.request_id})`);
  }
  return payload.data;
}

async function devLogin(realId) {
  csrfToken = (await api('/auth/csrf')).csrf_token;
  const profile = await api('/auth/dev-login', {
    method: 'POST', json: { real_id: realId },
  });
  csrfToken = (await api('/auth/csrf')).csrf_token;
  return profile;
}

// 仅在用户主动确认个人信息处理告知后调用。
async function confirmPrivacyConsent() {
  return api('/me/privacy-consent', { method: 'POST' });
}
```

## 4. 已实现接口

### 4.1 GET /healthz（公开）

数据库正常：200，`data={"status":"ok"}`；数据库不可用：503 `INTERNAL_ERROR`、`message="数据库不可用"`、`data=null`。不返回连接参数或底层异常。

### 4.2 GET /auth/csrf（公开）

200，`data={"csrf_token":"..."}`，同时设置 `csrftoken` Cookie。令牌为不透明字符串，不校验其固定文本长度，不写入业务日志。

### 4.3 POST /auth/dev-login（公开，仅开发环境）

请求为 JSON；仅 `DEBUG` 与 `ALLOW_DEV_LOGIN` 同时为真时可用，匿名登录也强制校验 CSRF。首次使用编号自动创建开发身份，重复使用同一编号复用账号；这不代表已实现正式自由注册或学校 SSO。

| 字段 | 必填 | 约束 |
| --- | --- | --- |
| real_id | 是 | 1～32 位字母、数字、下划线或短横线 |
| name | 否 | 非空字符串，最多 32 字；省略时取编号 |
| email | 否 | 合法邮箱，最多 254 字符；省略时生成 `<real_id>@tongji.edu.cn`，域名须在配置白名单内 |

未知字段、空值或格式错误返回 400；邮箱域名或身份冲突返回 401 `AUTH_FAILED`；停用账号返回 403。以 `t`/`T` 开头的编号临时映射为教师，其余为学生；新账号不会自动获得管理员权限。默认昵称为 `同学_` 加随机字符，不使用真实姓名。

200 返回本人资料，与 `GET /me` 相同；已有账号再次登录不借请求字段修改资料。管理员测试身份由受控后台配置，不接受前端提交 `is_admin`。

### 4.4 GET /me、PATCH /me

`GET /me`：200 返回本人资料。字段集合如下：

```json
{
  "uid": "0123456789abcdef0123456789abcdef",
  "nickname": "山间清风",
  "name": "陈同学",
  "role": "student",
  "is_admin": false,
  "email": "sprint1_sample@tongji.edu.cn",
  "email_notify_enabled": true,
  "privacy_consented": false
}
```

`PATCH /me` 接受 JSON 中的 `nickname`、`email_notify_enabled`，可只提供一项；当前实现允许 `{}` 原样返回资料。昵称去首尾空白后为 1～32 字；通知开关必须是 JSON 布尔值，字符串、数字及 `null` 不接受。只读字段与未知字段返回 400，成功返回更新后的本人资料。

`name`、`email` 只用于本人资料；招募发布者按业务关系可见的申请人姓名另按第 6 节裁剪，不能据此提供通用用户隐私查询接口。`email_notify_enabled=false` 不影响站内通知，真实邮件发送仍未接入。

### 4.5 POST /me/privacy-consent、POST /auth/logout

两者都要求登录及 CSRF，不要求业务请求体。隐私确认返回本人资料，`privacy_consented=true`；重复确认保持首次确认时间。登出返回 200、`data=null`，原会话随后访问 `/me` 返回 401。

### 4.6 GET /auth/sso/login、GET /auth/sso/callback（预留）

当前均返回 501，`code=INTERNAL_ERROR`、`message="预留"`、`data=null`。正式认证方案尚未确定，本次前端联调使用开发身份。

## 5. 招募目标契约（阶段 2，待实现）

### 5.1 标签与枚举

`GET /tags` 返回 200、`data={"items":[{"id":1,"name":"计算机"}]}`。仅返回启用标签，按 `sort_order, id` 升序，不分页；已有招募引用的停用标签仍可显示名称。

招募类型沿用现有模型：`competition`（竞赛）、`activity`（活动）、`internship`（实验室实习）。招募状态为 `open`（进行中）、`full`（已满员）、`closed`（已关闭）；删除由 `is_deleted` / `deleted_at` 表示，不新增第四种数据库状态。

### 5.2 招募请求字段

创建用 JSON；PATCH 只更新提供的字段，至少提供一个可写字段。未列出的字段均不可写，身份与状态由服务端决定。

| 字段 | POST | PATCH / 约束 |
| --- | --- | --- |
| title | 必填 | 去首尾空白后 1～100 字 |
| type | 必填 | 第 5.1 节的类型枚举 |
| description | 必填 | 去首尾空白后非空的纯文本，不解释为 HTML |
| tag_ids | 必填 | 非空、不重复的正整数数组；每项须为当前启用标签 ID |
| min_headcount | 可省略，默认 null | null 或正整数，非空时须不大于 max_headcount |
| max_headcount | 必填 | 1～50 的整数；更新后不得低于 accepted_count |
| deadline | 必填 | 带时区；严格晚于操作时刻，且不晚于该时刻加一个日历年，闰日按既有规则处理 |

PATCH 时用“已有值 + 提交值”一起验证人数范围；`min_headcount=null` 清空下限，省略则不变。`tag_ids` 提交后整体替换，省略则保留，包括已有的停用标签关联。不得提交 `publisher`、`accepted_count`、`status`、`deleted_at` 等只读字段。

请求示例；调用时须将截止时间替换为符合当时窗口的时间：

```json
{
  "title": "软件工程竞赛组队",
  "type": "competition",
  "description": "招募熟悉 Python 的队员共同完成竞赛项目。",
  "tag_ids": [1],
  "min_headcount": 2,
  "max_headcount": 3,
  "deadline": "2026-11-15T18:00:00+08:00"
}
```

### 5.3 招募响应字段

下述类型名用于描述 JSON 结构，不是新增数据库模型。

| 数据结构 | 字段 |
| --- | --- |
| PublicUser | `uid`、`nickname`、`role`；不含用户数据库主键、姓名、邮箱 |
| Tag | `id`、`name` |
| RecruitmentSummary | `id`、`title`、`type`、`tags: Tag[]`、`min_headcount`（可空）、`max_headcount`、`accepted_count`、`status`、`is_deleted`、`deadline`、`publisher: PublicUser`、`created_at`、`updated_at` |
| RecruitmentDetail | Summary 全部字段，加 `description`、`closed_at` / `full_at` / `close_reason`（可空）、`my_application`（可空）、`permissions`；仅发布者另有 `application_counts` |

`my_application` 为当前用户对该招募最近一次申请的 `{id, status}`，从未申请则为 null；撤回重投保留旧记录，但这里返回最新记录。过留存期后不返回申请明细。`application_counts` 包含五种申请状态的计数；清理前按记录统计，清理后仅使用已保存的聚合值，不重建明细。

`permissions` 为 `can_apply`、`can_edit`、`can_close`、`can_delete`、`can_view_applications` 布尔值，以及 `apply_blocked_reason`（可空）。投递被阻止时，原因按本人投递、隐私未确认、投递窗口关闭、已有未撤回申请的校验顺序，取对应业务错误码。前端用于按钮展示；写请求必须重新鉴权及校验，不能信任客户端传来的权限。

普通招募列表及详情排除已删除记录，返回的 `is_deleted=false`。申请历史通过自己的招募摘要表达删除状态，不因招募详情 404 而丢失申请记录。

待实现的详情 `data` 示例：当前用户为已确认隐私告知、尚未申请的普通浏览者。

```json
{
  "id": 101,
  "title": "软件工程竞赛组队",
  "type": "competition",
  "tags": [{"id": 1, "name": "计算机"}],
  "min_headcount": 2,
  "max_headcount": 3,
  "accepted_count": 0,
  "status": "open",
  "is_deleted": false,
  "deadline": "2026-11-15T18:00:00+08:00",
  "publisher": {"uid": "11111111111111111111111111111111", "nickname": "项目发起人", "role": "student"},
  "created_at": "2026-10-26T09:00:00+08:00",
  "updated_at": "2026-10-26T09:00:00+08:00",
  "description": "招募熟悉 Python 的队员共同完成竞赛项目。",
  "closed_at": null,
  "full_at": null,
  "close_reason": null,
  "my_application": null,
  "permissions": {
    "can_apply": true,
    "can_edit": false,
    "can_close": false,
    "can_delete": false,
    "can_view_applications": false,
    "apply_blocked_reason": null
  }
}
```

### 5.4 列表、详情及写操作

| 接口 | 输入与行为 | 成功 data |
| --- | --- | --- |
| GET /recruitments | `q`、`type`、`tag`、`status`、分页；默认展示所有未删除招募 | 分页 RecruitmentSummary |
| GET /me/recruitments | 同上，额外限定发布者为当前用户；包括关闭与满员，不包括删除 | 分页 RecruitmentSummary |
| GET /recruitments/{id} | 未删除的招募；不存在或已删除为 404 | RecruitmentDetail |
| POST /recruitments | 第 5.2 节请求；新建招募与标签同一事务提交 | 201，RecruitmentDetail |
| PATCH /recruitments/{id} | 仅发布者在 open 且未到截止时修改 | 200，RecruitmentDetail |
| POST /recruitments/{id}/close | 仅发布者在 open 且未到截止时关闭；空请求体或 `{}` | 200，RecruitmentDetail |
| DELETE /recruitments/{id} | 发布者受可编辑窗口限制，管理员可删除任意未删除招募；JSON `reason` 为字符串，管理员行使删除权限时必填且去空白后非空，普通发布者可省略 | 200，null |

`q` 对标题或描述做不区分大小写的包含搜索，去首尾空白，空串不筛选。`type/status` 为单一枚举，`tag` 为单个正整数标签 ID，多个条件取交集。无匹配标签正常返回空列表。排序为有效进行中在前，其余状态在后；各组按 `created_at DESC, id DESC` 稳定排序。类型、状态或标签参数空值/格式非法返回 400。

列表筛选、排序、详情的 `status` 使用同一时刻的有效状态：已满员优先，其余原 open 且到截止的表现为 closed。详情相应使用截止时间作为有效 `closed_at`，不把任务延迟当作仍可投递。写操作仍先调用既有补执行逻辑，再在锁内验证实际状态。

对象可见但非发布者编辑/关闭为 403；窗口不允许为 409 `RECRUITMENT_NOT_EDITABLE`。人数上限低于已接受人数为 409 `HEADCOUNT_BELOW_ACCEPTED`；等于时在同一事务进入 full 并拒绝其余处理中申请。重复删除已删除对象为 404，重复关闭已关闭对象为 409，不重复生成通知。

保留原有软删除：`deleted_at` 置为删除时间，`processing/accepted` 申请转为 `invalid`，已拒绝、已撤回不变，历史接受人数保留；不提供恢复功能。修改、关闭、删除的相关通知和审计按既有规则在事务中维护。

## 6. 申请与私有简历目标契约（阶段 3～4，待实现）

### 6.1 状态与数据结构

申请状态为 `processing`（处理中）、`accepted`（已接受）、`rejected`（已拒绝）、`withdrawn`（已撤回）、`invalid`（已失效）。暂留是发布者私有的 `publisher_mark=hold`，申请仍为 processing；未暂留为 `none`。

| 数据结构 | 字段 |
| --- | --- |
| RecruitmentReference | `id`、`title`、`type`、`status`、`is_deleted`、`deleted_at`（可空）；用于申请历史，不能据此绕过已删除招募详情的访问限制 |
| ApplicationSummary | `id`、`recruitment: RecruitmentReference`、`applicant: PublicUser`、`status`、`created_at`、`updated_at`、`decided_at`（可空）、`permissions`；发布者另按权限获得 `applicant.name`、`publisher_mark`、`has_unseen_update` |
| ApplicationDetail | Summary 全部字段，加按权限裁剪的 `note`（可空）、`resume: {name, size, type}`；size 为字节数，type 为 pdf/doc/docx |

列表不返回 `note` 或简历元数据。文件名来自服务端清洗结果，最多 255 个 UTF-8 字节；不返回存储路径或公开下载链接。`permissions` 含 `can_modify`、`can_withdraw`、`can_process`、`can_download_resume`；当前状态和身份不满足时为 false。

申请查询同样按服务端当前时刻解释状态：若数据库仍为 processing，但已到关闭后七天边界，响应应表现为 rejected，`decided_at` 为该边界时刻，修改/撤回/处理权限均为 false；不能直接用尚未补执行的数据库值生成按钮。该有效状态用于列表筛选、详情及状态统计，持久化和通知仍由状态补执行负责。

| 关系与状态（均在留存期内） | 申请记录 | 补充说明 | 简历元数据与文件 | 私有标记 / 未读修改 |
| --- | --- | --- | --- | --- |
| 申请人，processing/accepted/rejected | 可见 | 可见 | 可见 | 不返回 |
| 申请人，withdrawn/invalid | 可见 | 可见 | 不返回 | 不返回 |
| 发布者，processing/accepted/rejected | 可见，含申请人姓名 | 可见 | 可见 | 返回 |
| 发布者，withdrawn/invalid | 可见，含申请人姓名 | 不返回 | 不返回 | 不返回 |
| 无业务关系的用户或管理员 | 404 | 不返回 | 不返回 | 不返回 |
| 到达留存期限 | 双方 404，列表不返回该记录 | 不返回 | 不返回 | 不返回 |

申请人读取本人姓名使用 `/me`，不额外放宽申请对象的姓名字段策略。管理员本人恰为发布者或申请人时按该业务关系处理。撤回/失效后的简历限制同时适用于双方；已关闭招募或已拒绝申请不单独触发禁读。

待实现的详情 `data` 示例：发布者查看仍在处理窗口内的申请。

```json
{
  "id": 201,
  "recruitment": {
    "id": 101,
    "title": "软件工程竞赛组队",
    "type": "competition",
    "status": "open",
    "is_deleted": false,
    "deleted_at": null
  },
  "applicant": {"uid": "22222222222222222222222222222222", "nickname": "申请同学", "role": "student", "name": "陈同学"},
  "status": "processing",
  "created_at": "2026-10-26T09:30:00+08:00",
  "updated_at": "2026-10-26T10:00:00+08:00",
  "decided_at": null,
  "publisher_mark": "none",
  "has_unseen_update": true,
  "note": "熟悉 Django 和 PostgreSQL。",
  "resume": {"name": "简历.pdf", "size": 4096, "type": "pdf"},
  "permissions": {
    "can_modify": false,
    "can_withdraw": false,
    "can_process": true,
    "can_download_resume": true
  }
}
```

### 6.2 投递、列表、详情与下载（阶段 3）

| 接口 | 输入 / 权限 | 成功 data |
| --- | --- | --- |
| POST /recruitments/{id}/applications | multipart；必填一个 `resume` 文件，可选 `note` 字符串；本人不能申请自己的招募，须已确认隐私告知 | 201，ApplicationDetail |
| GET /recruitments/{id}/applications | 仅发布者；`status` 为单一申请状态，另有分页参数；删除后仍可在留存期内查看受限历史记录 | 分页 ApplicationSummary |
| GET /me/applications | 当前申请人；可按 `status`、`recruitment_id` 筛选，另有分页参数；包括撤回的旧记录 | 分页 ApplicationSummary |
| GET /applications/{id} | 仅申请人或发布者，遵守第 6.1 节权限 | ApplicationDetail |
| GET /applications/{id}/resume | 同一对象权限校验后，再检查 can_download_resume | 200，文件流，非信封 |

申请列表按 `created_at DESC, id DESC` 排序。`status` 非法或 `recruitment_id` 非正整数为 400；不存在或不属于本人的筛选结果为空。发布者申请列表的招募不存在、访问者不是发布者或已过留存期为 404；不能凭管理员身份查询。

`note` 省略或空串归一为 null，不从 multipart 文本 `"null"` 推断空值。简历只接受 PDF/DOC/DOCX，非空且不超过 10 MiB（10,485,760 字节），同时验证扩展名、实际大小及文件特征；客户端 MIME 不作为信任依据。缺失必填文件是 400 `VALIDATION_ERROR`，文件不合格是 400 `INVALID_RESUME_FILE`。

同一用户对同一招募最多存在一条未撤回申请，已接受或已拒绝后不能重投；撤回后可重新 POST，生成新 ID。本人投递、隐私未确认、窗口关闭、重复投递分别使用第 2.3 节错误码。已删除招募按 404 处理。

下载成功使用 `Content-Disposition: attachment` 和清洗后的文件名；Content-Type 分别为 `application/pdf`、`application/msword`、`application/vnd.openxmlformats-officedocument.wordprocessingml.document`。对象不可见返回 404；关系合法但 withdrawn/invalid 不可下载时返回 403；文件实际缺失返回 404，不暴露物理路径。发布者读取他人简历写审计，文件流仍携带请求 ID；敏感详情和下载响应须使用 `Cache-Control: private, no-store`。

上传示例（接口在阶段 3 完成后才可调用）：

```javascript
const form = new FormData();
form.append('resume', selectedFile);
form.append('note', noteText ?? '');
const response = await fetch(`/api/v1/recruitments/${recruitmentId}/applications`, {
  method: 'POST', credentials: 'same-origin',
  headers: { 'X-CSRFToken': csrfToken },
  body: form,
});
// 不手写 Content-Type；由浏览器生成 multipart boundary。
```

### 6.3 修改、撤回与处理（阶段 4）

`PATCH /applications/{id}` 使用 multipart，接受可选的 `note`、`resume`，至少提供一项。省略的字段不变，空字符串 note 清空说明，文件不能通过空值删除。仅申请人本人在申请仍为 processing 且招募未删除时可修改。成功 200 返回 ApplicationDetail，置未读修改标记并通知发布者；旧文件在事务成功提交后才清理，失败保留原文件。

以下动作使用 POST，除 read 外请求体为空或 `{}`；成功均为 200、ApplicationDetail：

| action | 操作者 | 行为与边界 |
| --- | --- | --- |
| withdraw | 申请人 | 与修改条件一致；转 withdrawn，关闭双方简历访问；再次投递走新建接口 |
| accept | 发布者 | 仅 processing 且在处理窗口、未满员时接受；增加 accepted_count，达到上限时进入 full 并拒绝剩余处理中申请 |
| reject | 发布者 | 仅 processing 且在处理窗口时拒绝；转 rejected，不增加人数 |
| hold | 发布者 | 仅 processing 且在处理窗口时标记 hold；不向申请人展示，不产生接受/拒绝通知 |
| unhold | 发布者 | 同上，标记恢复 none |
| read | 发布者 | 确认已查看的申请修改，见下文；不代表接受申请或读取通知 |

hold/unhold 在仍满足操作条件且标记已是目标值时返回当前记录，不重复产生业务副作用。其他终态操作不能重放：同一申请重复 accept/reject/withdraw 返回 409，不重复计数或通知。身份不符但对象可见为 403；对象不可见为 404。

状态操作先补执行招募到期及自动拒绝，再在招募锁、申请锁下校验。校验优先顺序为对象访问、操作者身份、申请是否 processing、招募处理窗口与人数；因此到期补执行已将申请拒绝后返回 `APPLICATION_NOT_PROCESSING`，不能要求前端只接受 `PROCESSING_WINDOW_CLOSED`。最后名额竞争最多一份申请成功。

**未读修改确认**：`GET /applications/{id}` 及列表不清除 `has_unseen_update`。发布者展示详情后显式调用 `POST /applications/{id}/read`，JSON 必填 `{"seen_updated_at":"2026-10-26T10:00:00+08:00"}`，使用刚读取详情的 `updated_at`。写服务在锁内比较时间点：版本一致才清除标记；期间出现新修改则保留标记，并返回当前详情供刷新。仅该确认不改变内容版本时间；重复确认无额外副作用。仍须遵守对象可见性及私有标记权限，withdrawn/invalid 不可确认。

此约定落实计划中的未读确认职责；旧实现草案中“GET 详情顺带清标记”的建议不作为实现依据，正式 HTTP 契约以本文为准。阶段 3 只提供读取，阶段 4 再交付确认写接口。

## 7. 通知目标契约（阶段 5，待实现）

Notification 对象为 `id`、`type`、`title`、`content`、`recruitment_id`（可空）、`application_id`（可空）、`is_read`、`created_at`。不返回接收人邮箱、私有文件信息、简历内容或申请人的完整身份；客户端跳转目标仍受目标接口的权限校验。

| 接口 | 输入与行为 | 成功 data |
| --- | --- | --- |
| GET /notifications | 仅当前用户；可选 `is_read=true/false`，另有分页参数；按 `created_at DESC, id DESC` | 分页 Notification |
| GET /notifications/unread-count | 当前用户当前可见的未读通知数 | `{"unread_count":0}` |
| POST /notifications/{id}/read | 空请求体或 `{}`，只能修改自己的通知；重复调用保持已读 | Notification |
| POST /notifications/read-all | 空请求体或 `{}`，只更新当前用户当前可见的未读通知 | `{"updated_count":0}`，返回本次实际更新条数 |

无权读取或修改他人的通知返回 404；`is_read` 空值、数字或其他字符串为 400。列表、未读数及标记操作采用一致的可见范围；到达申请留存期限的关联通知不再返回，也不计入未读数，不依赖物理清理任务是否已执行。标记全部已读不包括该操作完成后才新建的通知。

通知 type 沿用 `backend/apps/notifications/types.py`：`application_submitted`、`application_accepted`、`application_rejected`、`application_withdrawn`、`application_updated`、`recruitment_closed`、`recruitment_updated`、`recruitment_deleted`、`admin_removed`。应用列表/通知列表的读取不会自动标记通知已读。

## 8. 状态、事务与对接验收

### 8.1 时间与删除边界

- `now >= deadline` 停止新投递；未满员的关闭招募仅在 `now < closed_at + 7 天` 时允许发布者处理已有申请，到七天边界自动拒绝剩余 processing。
- 满员优先于关闭；处理中的申请被自动拒绝后不能修改或撤回。暂留不延长处理窗口。
- 删除将 processing/accepted 转 invalid；已接受申请的 `decided_at` 保留首次决定时间，失效时间取招募的 `deleted_at`。
- 留存期从 `closed_at`、`full_at`、`deleted_at` 最早的非空时间起算 180 天，后续操作不重新计时。到期即禁止申请明细、简历及关联通知访问；物理清理仍属预留工作。
- 读取不得清除未读标记。时间到期的展示状态、权限与筛选应一致；数据库状态补执行和通知由既有状态工具在写操作或同步命令中完成。

### 8.2 后续实现约束

新建招募使用独立事务保存招募与标签；已有招募及申请的写操作复用 `run_in_recruitment_tx`，不外包一层大事务，按招募锁 → 申请锁顺序执行。状态、人数、站内通知与审计在所属业务事务中保持一致；文件校验暂存位于事务外，失败清理新文件，成功后清理被替换旧文件。

读取与写入均复用对象权限，禁止通过前端隐藏按钮代替校验。申请详情、元数据与下载权限一致；响应结构以本文件为准，禁止直接将模型全字段序列化。阶段 2～5 实现时更新本文件的接口状态及对应示例，不能仅凭完成数据模型把接口标为已实现。

### 8.3 阶段 1 的验证边界

本阶段验证现有路由、响应信封、开发身份自动建号、登录后令牌轮换、会话退出、隐私确认幂等、字段拒绝及代理 Host/Origin 下的 CSRF 行为；目标接口的字段、权限、状态、错误码为后续阶段实现和回归依据。前端工程尚未建立，代理请求头验证不代表实际浏览器联调已完成。

已有测试集从 `backend/` 执行：`python manage.py test tests --keepdb --noinput --settings=config.settings.test`；使用项目专用测试数据库，不能指向正式或其他项目数据库。正式阶段完成情况写入 `Project_Progress_Record/Sprint1_BackEnd/Record/`，此处不维护个人部署记录。
