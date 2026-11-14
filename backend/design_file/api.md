# JiMeet 后端接口契约

更新日期：2026-11-14

本文是前后端对接的统一接口正文。下文接口路径统一以 `/api/v1` 为前缀，不带末尾斜杠；文件路径相对项目根目录。

## 1. 接口概览

当前实现 39 个方法/路径（含受开关控制的开发登录），另有 2 个返回 501 的 SSO 预留接口；关闭开发登录时可用路径为 38 个。招聘治理删除接口尚待实现，交付后累计 40 个；既有本人删除接口的语义适配不另计路径。

| 方法 | 路径 | 状态 |
| --- | --- | --- |
| GET | `/healthz` | 可用 |
| GET | `/auth/csrf` | 可用 |
| POST | `/auth/register` | 可用 |
| POST | `/auth/login` | 可用 |
| POST | `/auth/dev-login` | 仅开发环境 |
| POST | `/auth/logout` | 可用 |
| GET | `/me` | 可用 |
| PATCH | `/me` | 可用 |
| POST | `/me/privacy-consent` | 可用 |
| GET | `/auth/sso/login` | 预留（501） |
| GET | `/auth/sso/callback` | 预留（501） |
| GET | `/tags` | 可用 |
| GET | `/recruitments` | 可用 |
| POST | `/recruitments` | 可用 |
| GET | `/recruitments/{id}` | 可用 |
| PATCH | `/recruitments/{id}` | 可用 |
| DELETE | `/recruitments/{id}` | 可用；本人/治理分入口待阶段 4 适配 |
| DELETE | `/admin/recruitments/{id}` | 待实现（阶段 4，治理删除） |
| POST | `/recruitments/{id}/close` | 可用 |
| GET | `/me/recruitments` | 可用 |
| POST | `/recruitments/{id}/applications` | 可用 |
| GET | `/recruitments/{id}/applications` | 可用 |
| GET | `/me/applications` | 可用 |
| GET | `/applications/{id}` | 可用 |
| GET | `/applications/{id}/resume` | 可用 |
| PATCH | `/applications/{id}` | 可用 |
| POST | `/applications/{id}/withdraw` | 可用 |
| POST | `/applications/{id}/accept` | 可用 |
| POST | `/applications/{id}/reject` | 可用 |
| POST | `/applications/{id}/hold` | 可用 |
| POST | `/applications/{id}/unhold` | 可用 |
| POST | `/applications/{id}/read` | 可用 |
| GET | `/notifications` | 可用 |
| GET | `/notifications/unread-count` | 可用 |
| POST | `/notifications/{id}/read` | 可用 |
| POST | `/notifications/read-all` | 可用 |
| GET | `/announcements` | 可用 |
| GET | `/announcements/{id}` | 可用 |
| POST | `/announcements` | 可用 |
| PATCH | `/announcements/{id}` | 可用 |
| DELETE | `/announcements/{id}` | 可用（本人删除） |
| DELETE | `/admin/announcements/{id}` | 可用（治理删除） |

标注“待实现”的路径不可调用；阶段 4～5 的目标规则与当前行为在相应章节分别说明。

`/applications/{id}/read` 用于确认申请修改；通知已读使用 `/notifications/{id}/read` 或 `/notifications/read-all`。

正式身份认证（SSO）、真实邮件投递、聊天、推荐、通用用户主页和软删除恢复暂未提供。本轮（Sprint2）业务事件不再产生邮件任务，见第 7、9 章兼容说明。

### 1.1 运行约定

依赖见 `backend/requirements/base.txt`：Python 3.12+、PostgreSQL 15+，Django 6.1.2、DRF 3.18.3、psycopg 3.3.6。配置从进程环境变量读取，不自动加载 `.env`；变量清单见 `backend/.env.example`。

`seed_tags` 初始化标签；`run_sync_recruitments` 补执行到期关闭与七天自动拒绝，需要独立调用或调度。邮件发送与留存物理清理命令仍为预留，调用返回 `CommandError: reserved`；Sprint2 起业务事件不再创建邮件待发记录（见第 7 章兼容说明）。

受控账号管理：`grant_admin` / `revoke_admin` 按邮箱授予或撤销业务管理员，锁定目标账号并与审计同事务提交，重复操作不重复记录状态变化。`init_password` 仅初始化无可用密码的账号，拒绝覆盖已有密码，复用注册的 8～128 字符及相似度策略；支持终端无回显输入或标准输入管道，不接收密码参数。三类命令失败均回滚账号变更。不提供在线授予或仅凭邮箱重设密码的入口。

## 2. 通用契约

### 2.1 请求、标识与时间

- 默认要求登录；仅健康检查、CSRF 获取、邮箱注册/登录、开发登录及 SSO 占位接口公开。学生和教师使用同一业务操作规则，管理员身份不增加申请内容、简历读取权限。
- JSON 请求使用 `Content-Type: application/json`；上传和替换简历使用 `multipart/form-data`。文件下载成功返回文件流。
- JSON 字段使用 `snake_case`。用户仅暴露 32 位十六进制 `uid`；招募、申请、通知、标签使用正整数 `id`。不输出用户数据库主键、`real_id`、认证标识、私有文件路径或邮箱等无关身份信息。
- 时间为带时区的 ISO 8601 字符串，例如 `2026-11-15T18:00:00+08:00`，客户端按时间点解析；不能依赖固定时区文本。截止边界以服务端时间为准。
- 下文“省略字段”与值为 `null` 不同：无权读取的字段省略；有权读取但没有值的字段返回 `null`。列表无结果返回空数组。
- 声明输入字段的接口拒绝未知、只读字段。JSON 人数及资源 ID 接受整数，拒绝布尔值、浮点数和数字字符串；具体字段约束见各接口。
- `/me`、标签、招募、申请、私有简历和通知接口采用严格查询校验：未知或重复键返回 400。健康检查、会话辅助及 SSO 预留接口不使用查询参数。
- 资源不存在或对当前用户不可见时返回 404，具体删除与留存边界见对应接口。

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
| AUTH_FAILED | 401 | 登录凭据不合法（不存在邮箱、错误或不可用密码统一返回，不泄露账号是否存在）、开发身份不合法、身份或邮箱冲突 |
| FORBIDDEN | 403 | 无权执行操作、CSRF 校验失败或账号停用 |
| NOT_FOUND | 404 | 资源不存在、已删除或对访问者不可见 |
| VALIDATION_ERROR | 400 | 字段、查询参数或 JSON 格式错误 |
| VALIDATION_ERROR | 415 | 请求使用了该接口不支持的媒体类型 |
| METHOD_NOT_ALLOWED | 405 | 路径存在，但不支持该方法 |
| RATE_LIMITED | 429 | 注册或登录失败次数超限，窗口（600 秒）内拒绝，稍后自动恢复 |
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
| SSO_UNAVAILABLE | 503 | 正式 SSO 故障预留码，当前不使用 |

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

使用 Vite 开发代理时，可将以下配置合入前端工程：

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

保留 Host 后，浏览器 Origin 与 Django 看到的请求 origin 一致，通常无需 `CSRF_TRUSTED_ORIGINS`。若代理必须改写 Host，则后端应仅将实际前端 origin（含协议与端口）加入该环境变量；重启后端使配置生效。**仅配置 CSRF 信任来源不等于启用 CORS**。同源代理保留 CSRF 保护；跨域部署需另外配置 CORS，生产环境还需核验 HTTPS 与代理设置。

参考：[Vite 开发代理](https://vite.dev/config/server-options#server-proxy)、[Django CSRF 来源校验](https://docs.djangoproject.com/en/6.1/ref/csrf/)。

### 3.2 Session、CSRF 与隐私确认顺序

1. `GET /auth/csrf` 获取 `data.csrf_token` 并接收 `csrftoken` Cookie。
2. `POST /auth/dev-login` 携带 Cookie、JSON 身份和 `X-CSRFToken`。
3. 登录成功会建立 `sessionid` 并轮换 CSRF 密钥；再次 `GET /auth/csrf` 更新前端持有的令牌。
4. `GET /me` 读取本人身份及 `privacy_consented`。**只有用户明确确认告知后**才调用 `POST /me/privacy-consent`；登录不等于同意，不能自动确认。
5. 后续 POST/PATCH/DELETE 携带当前 CSRF 令牌。退出后丢弃前端缓存的本人资料；再次登录重新走上述流程。

`sessionid` 为 HttpOnly Cookie，前端不读取、不复制到请求体或本地存储；`fetch` 使用 `credentials: 'same-origin'`。接口返回的 masked CSRF token 和当前 `csrftoken` Cookie 值均可用于请求头，但登录前的旧令牌不可继续使用。实际规则见 [Django CSRF 文档](https://docs.djangoproject.com/en/6.1/ref/csrf/)。

面向普通用户的注册登录（4.3、4.4）替代上文第 2 步的开发登录作为主链路：仍先取 CSRF，注册或登录成功后重新 `GET /auth/csrf` 刷新前端令牌；开发登录仅在开发开关下供隔离联调，不得替代正式注册登录验收。

浏览器调用示例：

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

## 4. 基础与账号接口

### 4.1 GET /healthz（公开）

数据库正常：200，`data={"status":"ok"}`；数据库不可用：503 `INTERNAL_ERROR`、`message="数据库不可用"`、`data=null`。不返回连接参数或底层异常。

### 4.2 GET /auth/csrf（公开）

200，`data={"csrf_token":"..."}`，同时设置 `csrftoken` Cookie。令牌为不透明字符串，不校验其固定文本长度，不写入业务日志。

### 4.3 POST /auth/register（公开，强制 CSRF）

注册是面向普通用户的主入口。请求为 JSON：

| 字段 | 必填 | 约束 |
| --- | --- | --- |
| email | 是 | 合法邮箱，最多 254 字符；去首尾空白并按小写规范化后，域名须精确等于 `tongji.edu.cn` |
| password | 是 | 8～128 字符；须通过 Django 密码验证器（与邮箱/姓名不相似、非常见弱密码、非纯数字） |
| name | 是 | 去首尾空白后 1～32 字；仅作未核验展示信息，不作授权依据 |
| nickname | 否 | 1～32 字；缺省由服务端生成 `同学_` + 随机字符，不取自真实姓名或邮箱前缀 |
| role | 否 | `student`（默认）或 `teacher`，仅作展示与称谓标签 |

行为与错误：

- 成功 201：创建普通账号（`is_admin=false`、`privacy_consented=false`）、建立会话并轮换会话键与 CSRF 令牌；返回本人资料（字段同 `GET /me`），不返回密码摘要或内部认证标识（`real_id`、`sso_subject` 等）。内部兼容标识由服务端生成，客户端不可指定。
- 未知字段或携带 `is_admin`、`is_staff` 等权限字段：400 `VALIDATION_ERROR`，不建账号、不赋权。
- 邮箱已存在（含大小写变体与并发重复注册）：400 `VALIDATION_ERROR`，`data.details.email` 提示已注册；不覆盖已有账号的密码、身份绑定或权限。
- 邮箱或密码不合规：400 `VALIDATION_ERROR`，`details` 指明字段规则。
- 失败限流与 CSRF 校验同 4.4 口径；超限 429 `RATE_LIMITED`。
- 不发送认证邮件或验证码；响应、日志不记录密码、密码摘要或会话凭证。响应带 `Cache-Control: private, no-store`。

### 4.4 POST /auth/login（公开，强制 CSRF）

请求为 JSON：

| 字段 | 必填 | 约束 |
| --- | --- | --- |
| email | 是 | 同注册的邮箱规范化规则 |
| password | 是 | 字符串，1～128 字符 |

行为与错误：

- 成功 200：建立会话并轮换会话键与 CSRF 令牌，返回本人资料。
- 不存在邮箱、错误密码、不可用密码：统一 401 `AUTH_FAILED`，提示一致，不泄露账号是否存在。
- 凭据正确但账号已停用：403 `FORBIDDEN`，不建立会话。
- **失败限流**：注册与登录分别计数；邮箱与来源 IP 的键均只保存 SHA-256 摘要。窗口为 600 秒，同一邮箱键累计 5 次或同一 IP 键累计 20 次失败后返回 429 `RATE_LIMITED`，窗口滑过后恢复；成功注册或登录清除对应操作的邮箱键计数。字段校验、密码策略、重复注册及认证失败均计数，每次失败对有效邮箱键与 IP 各累计一次；邮箱缺失或不可解析、JSON 格式错误只按 IP 计数。CSRF 或不支持的媒体类型被拒绝时不计入认证失败。计数落库，并发失败不丢计数。
- 匿名请求同样强制 CSRF 校验；失败不写入会话。

### 4.5 POST /auth/dev-login（公开，仅开发环境）

请求为 JSON；仅 `DEBUG` 与 `ALLOW_DEV_LOGIN` 同时为真时可用，匿名登录也强制校验 CSRF。首次使用编号自动创建开发身份，重复使用同一编号复用账号；该入口仅用于开发身份联调。

| 字段 | 必填 | 约束 |
| --- | --- | --- |
| real_id | 是 | 1～32 位字母、数字、下划线或短横线 |
| name | 否 | 非空字符串，最多 32 字；省略时取编号 |
| email | 否 | 合法邮箱，最多 254 字符；省略时生成 `<real_id>@tongji.edu.cn`，域名须在配置白名单内 |

未知字段、空值或格式错误返回 400；邮箱域名或身份冲突返回 401 `AUTH_FAILED`；停用账号返回 403。以 `t`/`T` 开头的编号临时映射为教师，其余为学生；新账号不会自动获得管理员权限。默认昵称为 `同学_` 加随机字符，不使用真实姓名。

200 返回本人资料，与 `GET /me` 相同；已有账号再次登录不借请求字段修改资料。管理员测试身份由受控后台配置，不接受前端提交 `is_admin`。

### 4.6 GET /me、PATCH /me

`GET /me`、`PATCH /me` 均不接受 URL 查询参数。通过会话认证（写请求还需 CSRF 校验）后，未知或重复查询键返回 400 `VALIDATION_ERROR`，不执行资料更新。两种请求的响应均设置 `Cache-Control: private, no-store`。

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

`PATCH /me` 仅接受 `application/json` 请求体中的 `nickname`、`email_notify_enabled`，可只提供一项；允许 `{}` 原样返回资料。昵称去首尾空白后为 1～32 字；通知开关必须是 JSON 布尔值，字符串、数字及 `null` 不接受。只读字段与未知字段返回 400，成功返回更新后的本人资料。

`name`、`email` 只用于本人资料；招募发布者按业务关系可见的申请人姓名另按第 6 节裁剪，不能据此提供通用用户隐私查询接口。`email_notify_enabled=false` 不影响站内通知，真实邮件发送仍未接入。

### 4.7 POST /me/privacy-consent、POST /auth/logout

两者都要求登录及 CSRF，不要求业务请求体。隐私确认返回本人资料，`privacy_consented=true`；重复确认保持首次确认时间。登出返回 200、`data=null`，原会话随后访问 `/me` 返回 401。

### 4.8 GET /auth/sso/login、GET /auth/sso/callback（预留）

当前均返回 501，`code=INTERNAL_ERROR`、`message="预留"`、`data=null`。正式认证尚未接入，开发联调使用开发登录入口。

## 5. 招募接口

### 5.1 标签与枚举

`GET /tags` 返回 200、`data={"items":[{"id":1,"name":"计算机"}]}`。仅返回启用标签，按 `sort_order, id` 升序，不分页；已有招募引用的停用标签仍可显示名称。

招募类型为：`competition`（竞赛）、`activity`（活动）、`internship`（实验室实习）。招募状态为 `open`（进行中）、`full`（已满员）、`closed`（已关闭）；删除状态由 `is_deleted` / `deleted_at` 表示。

### 5.2 招募请求字段

创建用 JSON；PATCH 只更新提供的字段，至少提供一个可写字段。未列出的字段均不可写，身份与状态由服务端决定。

| 字段 | POST | PATCH / 约束 |
| --- | --- | --- |
| title | 必填 | 去首尾空白后 1～100 字 |
| type | 必填 | 第 5.1 节的类型枚举 |
| description | 必填 | 去首尾空白后非空的纯文本，不解释为 HTML |
| tag_ids | 必填 | 非空、不重复的正整数数组；每项须为当前启用标签 ID |
| min_headcount | 可省略，默认 null | null 或正整数，非空时须不大于 max_headcount |
| max_headcount | 必填 | 正整数。**目标契约 1～200（阶段 4 实施）**；当前实现仍限制 1～50，错误文案随实现值。更新后不得低于 accepted_count |
| deadline | 必填 | 带时区；严格晚于操作时刻，且不晚于该时刻加一个日历年，闰日回退至次年的 2 月 28 日 |

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

下述类型名用于描述响应 JSON 结构。

| 数据结构 | 字段 |
| --- | --- |
| PublicUser | `uid`、`nickname`、`role`；不含用户数据库主键、姓名、邮箱 |
| Tag | `id`、`name` |
| RecruitmentSummary | `id`、`title`、`type`、`tags: Tag[]`、`min_headcount`（可空）、`max_headcount`、`accepted_count`、`status`、`is_deleted`、`deadline`、`publisher: PublicUser`、`created_at`、`updated_at` |
| RecruitmentDetail | Summary 全部字段，加 `description`、`closed_at` / `full_at` / `close_reason`（可空）、`my_application`（可空）、`permissions`；仅发布者另有 `application_counts` |

`my_application` 为当前用户对该招募最近一次申请的 `{id, status}`，从未申请则为 null；撤回重投保留旧记录，但这里返回最新记录。长期记录不因固定期限隐藏（见 9.1）。`application_counts` 包含五种申请状态的计数；按现存记录统计，物理清理（预留）执行后仅使用已保存的聚合值，不重建明细。

`permissions` 为 `can_apply`、`can_edit`、`can_close`、`can_delete`、`can_view_applications` 布尔值，以及 `apply_blocked_reason`（可空）。投递被阻止时，原因按本人投递、隐私未确认、投递窗口关闭、已有未撤回申请的校验顺序，取对应业务错误码。前端用于按钮展示；写请求必须重新鉴权及校验，不能信任客户端传来的权限。

普通招募列表及详情排除已删除记录，返回的 `is_deleted=false`。申请历史通过自己的招募摘要表达删除状态，不因招募详情 404 而丢失申请记录。

招募详情 `data` 示例：当前用户为已确认隐私告知、尚未申请的普通浏览者。

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
| DELETE /recruitments/{id} | **本人删除**：仅发布者身份，受进行中且未删除的状态窗口限制；即使发布者拥有管理员标记也不绕过限制；JSON `reason` 可选（1～500 字）。阶段 4 适配为该纯本人语义 | 200，null |
| DELETE /admin/recruitments/{id} | **治理删除**（阶段 4 交付）：当前管理员可处置任意未删除状态的招聘；JSON `reason` 必填 1～500 字；与本人删除使用不同操作入口 | 200，null |

`q` 对标题或描述做不区分大小写的包含搜索，去首尾空白，空串不筛选。`type/status` 为单一枚举，`tag` 为单个正整数标签 ID，多个条件取交集。无匹配标签正常返回空列表。排序为有效进行中在前，其余状态在后；各组按 `created_at DESC, id DESC` 稳定排序。类型、状态或标签参数空值/格式非法返回 400。

列表筛选、排序、详情的 `status` 使用同一时刻的有效状态：已满员优先，其余原 open 且到截止的表现为 closed。详情相应使用截止时间作为有效 `closed_at`，不把任务延迟当作仍可投递。写操作仍先调用既有补执行逻辑，再在锁内验证实际状态。

对象可见但非发布者编辑/关闭为 403；窗口不允许为 409 `RECRUITMENT_NOT_EDITABLE`。人数上限低于已接受人数为 409 `HEADCOUNT_BELOW_ACCEPTED`；等于时在同一事务进入 full 并拒绝其余处理中申请。重复删除已删除对象为 404，重复关闭已关闭对象为 409，不重复生成通知。

软删除规则：`deleted_at` 置为删除时间，`processing/accepted` 申请转为 `invalid`，已拒绝、已撤回不变，历史接受人数保留；不提供恢复功能。

**通知接收范围：** 招募修改或删除只通知变更前仍为 processing/accepted 的申请人，已撤回或已拒绝者不再通知。调低人数上限触发满员时，相关申请人收到招募变更通知，剩余处理中申请另收到自动拒绝结果。管理员删除还向发布者发送治理删除通知；手动关闭向发布者发送明确的手动关闭通知，不立即拒绝已有申请。删除审计、通知及业务变更同事务提交，权限拒绝沿用公共审计处理。

## 6. 申请与私有简历接口

### 6.1 状态与数据结构

申请状态为 `processing`（处理中）、`accepted`（已接受）、`rejected`（已拒绝）、`withdrawn`（已撤回）、`invalid`（已失效）。暂留是发布者私有的 `publisher_mark=hold`，申请仍为 processing；未暂留为 `none`。

| 数据结构 | 字段 |
| --- | --- |
| RecruitmentReference | `id`、`title`、`type`、`status`、`is_deleted`、`deleted_at`（可空）；用于申请历史，不能据此绕过已删除招募详情的访问限制 |
| ApplicationSummary | `id`、`recruitment: RecruitmentReference`、`applicant: PublicUser`、`status`、`created_at`、`updated_at`、`decided_at`（可空）、`permissions`；发布者另按权限获得 `applicant.name`、`publisher_mark`、`has_unseen_update` |
| ApplicationDetail | Summary 全部字段，加按权限裁剪的 `note`（可空）、`resume: {name, size, type}`；size 为字节数，type 为 pdf/doc/docx |

列表不返回 `note` 或简历元数据。文件名来自服务端清洗结果，最多 255 个 UTF-8 字节；不返回存储路径或公开下载链接。`permissions` 含 `can_modify`、`can_withdraw`、`can_process`、`can_download_resume`；当前状态和身份不满足时为 false。这些值用于前端操作展示，写请求仍由服务端重新校验。

申请查询同样按服务端当前时刻解释状态：若数据库仍为 processing，但已到关闭后七天边界，响应应表现为 rejected，`decided_at` 为该边界时刻，修改/撤回/处理权限均为 false；不能直接用尚未补执行的数据库值生成按钮。该有效状态用于列表筛选、详情及状态统计，持久化和通知仍由状态补执行负责。

| 关系与状态 | 申请记录 | 补充说明 | 简历元数据与文件 | 私有标记 / 未读修改 |
| --- | --- | --- | --- | --- |
| 申请人，processing/accepted/rejected | 可见 | 可见 | 可见 | 不返回 |
| 申请人，withdrawn/invalid | 可见 | 可见 | 不返回（本人下载保留简历按 FR-04 例外允许） | 不返回 |
| 发布者，processing/accepted/rejected | 可见，含申请人姓名 | 可见 | 可见 | 返回 |
| 发布者，withdrawn/invalid | 可见，含申请人姓名 | 不返回 | 不返回（撤回/招聘删除后发布者禁读） | 不返回 |
| 无业务关系的用户或管理员 | 404 | 不返回 | 不返回 | 不返回 |

固定留存期限行已按 Sprint2 口径移除：不存在“到期即双方 404”的固定 180 天规则；长期记录的可见性仅由上表关系与状态决定。当前实现的旧截断及其移除进度见 9.1。

申请人读取本人姓名使用 `/me`，不额外放宽申请对象的姓名字段策略。管理员本人恰为发布者或申请人时按该业务关系处理。撤回/失效后的简历限制同时适用于双方；已关闭招募或已拒绝申请不单独触发禁读。

详情 `data` 示例：发布者查看仍在处理窗口内的申请；`has_unseen_update=true` 表示已有修改标记，新提交的该标记默认为 false。

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

### 6.2 投递、列表、详情与下载

| 接口 | 输入 / 权限 | 成功 data |
| --- | --- | --- |
| POST /recruitments/{id}/applications | multipart；必填一个 `resume` 文件，可选 `note` 字符串；本人不能申请自己的招募，须已确认隐私告知 | 201，ApplicationDetail |
| GET /recruitments/{id}/applications | 仅发布者；`status` 为单一申请状态，另有分页参数；删除后仍可在留存期内查看受限历史记录 | 分页 ApplicationSummary |
| GET /me/applications | 当前申请人；可按 `status`、`recruitment_id` 筛选，另有分页参数；包括撤回的旧记录 | 分页 ApplicationSummary |
| GET /applications/{id} | 仅申请人或发布者，遵守第 6.1 节权限 | ApplicationDetail |
| GET /applications/{id}/resume | 同一对象权限校验后，再检查 can_download_resume | 200，文件流，非信封 |

申请列表按 `created_at DESC, id DESC` 排序。`status` 非法或 `recruitment_id` 非正整数为 400；不存在或不属于本人的筛选结果为空。发布者申请列表的招募不存在或访问者不是发布者为 404；不能凭管理员身份查询。

`note` 去首尾空白后，省略或空串归一为 null，不从 multipart 文本 `"null"` 推断空值。上传不接受未知字段、重复字段或多个同名文件。简历只接受 PDF/DOC/DOCX，非空且不超过 10 MiB（10,485,760 字节），同时验证扩展名、实际大小及文件特征；客户端 MIME 不作为信任依据。缺失必填文件是 400 `VALIDATION_ERROR`，文件不合格是 400 `INVALID_RESUME_FILE`。

同一用户对同一招募最多存在一条未撤回申请，已接受或已拒绝后不能重投；撤回后可重新 POST，生成新 ID。本人投递、隐私未确认、窗口关闭、重复投递分别使用第 2.3 节错误码。已删除招募按 404 处理。

下载成功使用 `Content-Disposition: attachment` 和清洗后的文件名；Content-Type 分别为 `application/pdf`、`application/msword`、`application/vnd.openxmlformats-officedocument.wordprocessingml.document`。对象不可见返回 404；关系合法但 withdrawn/invalid 不可下载时返回 403；文件实际缺失返回 404，不暴露物理路径。发布者读取他人简历写审计，文件流仍携带请求 ID；敏感详情和下载响应须使用 `Cache-Control: private, no-store`。

上传示例：

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

### 6.3 修改、撤回与处理

`PATCH /applications/{id}` 使用 multipart，接受可选的 `note`、`resume`，至少提供一项。省略的字段不变，空字符串 note 清空说明，文件不能通过空值删除。仅申请人本人在申请仍为 processing 且招募未删除时可修改。成功 200 返回 ApplicationDetail，置未读修改标记并通知发布者；旧文件在事务成功提交后才清理，失败保留原文件。

成功的申请修改、撤回、接受、拒绝及实际改变暂留标记的操作，均在业务事务中写入 `application_update` 审计记录；重复暂留/取消暂留和只读已阅确认不另记。审计不保存申请说明或简历内容。

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

## 7. 通知接口

Notification 对象为 `id`、`type`、`title`、`content`、`recruitment_id`（可空）、`application_id`（可空）、`announcement_id`（可空）、`is_read`、`created_at`。不返回接收人邮箱、私有文件信息、简历内容或申请人的完整身份；客户端跳转目标仍受目标接口的权限校验。

| 接口 | 输入与行为 | 成功 data |
| --- | --- | --- |
| GET /notifications | 仅当前用户；可选 `is_read=true/false`，另有分页参数；按 `created_at DESC, id DESC` | 分页 Notification |
| GET /notifications/unread-count | 当前用户当前可见的未读通知数 | `{"unread_count":0}` |
| POST /notifications/{id}/read | 空请求体或 `{}`，只能修改自己的通知；重复调用保持已读 | Notification |
| POST /notifications/read-all | 空请求体或 `{}`，只更新当前用户当前可见的未读通知 | `{"updated_count":0}`，返回本次实际更新条数 |

无权读取或修改他人的通知返回 404；`is_read` 空值、数字或其他字符串为 400。列表、未读数及标记操作采用一致的可见范围；通知不因固定留存期限隐藏（9.1 目标口径，阶段 5 移除既有截断），可见性仅由接收人、目标关联权限与删除提示规则决定。标记全部已读不包括该操作完成后才新建的通知。

通知 type 沿用 `backend/apps/notifications/types.py`：`application_submitted`、`application_accepted`、`application_rejected`、`application_withdrawn`、`application_updated`、`recruitment_closed`、`recruitment_updated`、`recruitment_deleted`、`admin_removed`，以及 `announcement_admin_removed`（公告被管理员治理删除，接收人为公告作者，含公告名称、处置结果、原因与 `announcement_id` 引用）。读取申请列表或通知列表不会自动标记通知已读。

目标关联规则（阶段 3 起在数据层校验）：`announcement_id` 非空时 `recruitment_id`、`application_id` 必须为空；`application_id` 非空时 `recruitment_id` 必须非空；旧通知数据保持兼容。已删除目标的通知仍可见并展示删除提示，跳转目标接口仍按 404/权限校验，不恢复已删除内容的公开详情。

**邮件兼容（Sprint2）：** 业务事件只生成站内通知，不再创建 `EmailLog(PENDING)`、不再挂接派发回调；`email_notify_enabled` 保留为兼容字段，不控制任何发信行为，新前端不得展示为可用邮件通知功能。`email_log` 表及历史数据保留。

## 8. 公告接口（FR-09）

状态：HTTP 层已于 Sprint2 阶段 3 交付（视图、序列化、路由与业务锁内复核）。表结构见 `backend/design_file/design_manuscript/database.md` 1.9。

Announcement 对象字段：`id`、`title`、`content`、`time_kind`（`deadline` 报名截止时间 / `event` 活动时间）、`event_at`、`link_url`（可空）、`recruitment_id`（可空）、`recruitment_available`（布尔，关联招募当前是否可用）、`is_pinned`（只读）、`created_at`、`updated_at`、`author`（PublicUser：`uid`、`nickname`、`role`）与 `permissions`。不返回 `real_id`、邮箱等内部信息。

`permissions` 区分两种删除入口：`can_edit`（当前管理员且为作者）、`can_delete`（同 `can_edit`，本人删除入口）、`can_govern_delete`（当前管理员，治理删除入口）。写请求仍由服务端重新鉴权。

字段约束（去首尾空白后计数）：

| 字段 | POST | PATCH / 约束 |
| --- | --- | --- |
| title | 必填 | 1～100 字 |
| content | 必填 | 纯文本（不解释为 HTML），1～5000 字 |
| time_kind | 必填 | `deadline` 或 `event` |
| event_at | 必填 | 带时区 ISO 8601；不限制必须晚于当前时间；已过时间不自动等于已删除，编辑不因历史时间被拒绝 |
| link_url | 可选，可显式 null 清空 | 最多 500 字，仅 `http://`、`https://` 绝对地址 |
| recruitment_id | 可选，可显式 null 清空 | 正整数；写入时须存在且未删除；此后该招募被删除/关闭/满员不影响公告保留 |

`is_pinned` 为数据库保留字段，本轮 HTTP 不提供置顶能力：不可写、不参与排序与筛选。未知字段、`is_pinned` 写入、只读字段提交均返回 400。

| 接口 | 权限 | 输入与行为 | 成功 data |
| --- | --- | --- | --- |
| GET /announcements | 已登录 | 仅未删除；按 `created_at DESC, id DESC` 稳定分页；分页参数 page、page_size | 分页 Announcement |
| GET /announcements/{id} | 已登录 | 不存在或已删除为 404 | Announcement |
| POST /announcements | 当前 `is_admin` | 字段校验如上；成功 201 | 201，Announcement |
| PATCH /announcements/{id} | 当前 `is_admin` 且为作者 | 部分更新，至少一个可写字段；其他管理员不能编辑 | 200，Announcement |
| DELETE /announcements/{id} | 当前 `is_admin` 且为作者 | **本人删除**：软删除，不需要原因，不产生通知 | 200，null |
| DELETE /admin/announcements/{id} | 当前 `is_admin` | **治理删除**：JSON `reason` 必填 1～500 字；同一事务完成软删除、审计与作者站内通知（`announcement_admin_removed`） | 200，null |

行为与错误口径：

- 未登录 401；非作者编辑/本人删除、非管理员写入 403；对象不存在或已删除 404（含重复删除：不重复写审计与通知）；集合路径不支持的方法（如对 `/announcements` 的 PATCH/DELETE）405 `METHOD_NOT_ALLOWED`。
- 写操作在行锁内重新读取对象并复核状态与权限：更新与删除并发时不允许“删除后被更新复活”，后到请求按 404 处理。
- 管理员权限按请求实时读取；作者被撤销管理员权限后，发布、编辑、本人删除与治理删除全部拒绝（含其旧会话）。
- 每次发布、编辑、本人删除在同一事务内写入审计 `announcement_publish`、`announcement_update`、`announcement_delete`（`target_type=announcement`）；治理删除的 `reason` 写入审计的 `reason`。
- 正常发布、编辑、本人删除不产生站内通知或邮件；仅治理删除向作者发送一条通知。
- 关联招募被删除、关闭或满员后公告仍保留；`recruitment_available` 表达链接当前可用性，已删除招募的详情不因公告而恢复可见。

## 9. 状态与一致性规则

### 9.1 时间与删除边界

- `now >= deadline` 停止新投递；未满员的关闭招募仅在 `now < closed_at + 7 天` 时允许发布者处理已有申请，到七天边界自动拒绝剩余 processing。
- 满员优先于关闭；处理中的申请被自动拒绝后不能修改或撤回。暂留不延长处理窗口。
- 删除将 processing/accepted 转 invalid；已接受申请的 `decided_at` 保留首次决定时间，失效时间取招募的 `deleted_at`。
- **留存（Sprint2 目标口径）：** 不设固定 180 天清理或隐藏；满足对象关系与状态权限的历史申请、简历与通知长期可查，七天处理窗口、归属校验、删除提示与敏感字段裁剪规则不变。**实施状态：** 申请、简历与通知查询中的固定 180 天截断由阶段 4/5 适配移除；在此之前这些接口仍按旧截断行为过滤，差异以本条为准，前端不得据旧截断实现“过期即不可见”的产品语义。物理清理仍属预留工作，历史数据不重置。
- 读取不得清除未读标记。时间到期的展示状态、权限与筛选应一致；数据库状态补执行和通知由既有状态工具在写操作或同步命令中完成。

### 9.2 事务与资源一致性

新建招募与标签关联原子保存。已有招募及申请的写操作先独立提交必要的到期状态补执行，再按招募锁、申请锁的顺序执行业务事务。业务校验失败不撤销已提交的到期状态；状态、人数及产生的通知和审计随业务事务提交或回滚。

申请提交先检查身份与隐私确认，再校验并暂存文件；业务失败清理新文件，简历替换提交成功后才尝试清理旧文件。提交后的邮件调度异常仅记录日志，不回滚已提交申请、简历引用或待发邮件记录。

列表在分页前过滤对象归属及留存期限，与详情使用相同的时间状态投影。简历下载在短事务内复核权限、打开文件并记录发布者查看审计，文件传输在事务外进行。GET 请求不代替状态同步或显式已读操作。
