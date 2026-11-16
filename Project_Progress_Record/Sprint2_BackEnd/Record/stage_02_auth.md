# Sprint2 后端阶段 2 记录：邮箱密码注册登录与管理员配置

日期：2026-11-14｜分工：zf｜执行依据：[Sprint2 后端开发规划](../Plan/sprint2_backend_plan.md) 阶段 2、[阶段 1 记录](stage_01_baseline.md) 冻结的契约与参数｜状态：已完成

后续边界修正与补充验证见 [阶段 1～3 修正记录](stage_01_03_review_fixes.md)；本文保留原交付批次的测试结果。

## 1. 范围

实现 `POST /auth/register`、`POST /auth/login` 及会话建立；失败限流；受控管理员授予/撤销与历史账号密码初始化；保留开发登录与 SSO 预留的配置边界。接口契约按阶段 1 冻结值实现，未另行设定参数。

## 2. 核心修改

### 2.1 账号（`backend/apps/accounts/`）

- `models.py` 新增 `AuthFailure`（`auth_failure` 表，迁移 `0002_authfailure`）：限流键 SHA-256 摘要、操作类型、失败时间；插入即计数，并发失败不丢计数，对应 database.md 4.2。
- `ratelimit.py`：600 秒窗口、邮箱键 5 次 / IP 键 20 次阈值，超限 429 `RATE_LIMITED`；成功注册/登录清除邮箱键计数；窗口外记录惰性清理。
- `backends.py` 新增 `EmailPasswordBackend`：按规范化邮箱校验密码（复用 Django 哈希与验证器）；凭据正确但停用的账号也返回，由服务层按 403 口径处理，与“凭据错误统一 401”区分。已登记进 `AUTHENTICATION_BACKENDS`。
- `services.py` 新增 `register_with_password`、`login_with_password`：
  - 注册：邮箱去空白小写化、域名精确校验、Django 密码验证器（相似性/最短 8 位/常见弱密码/纯数字）、姓名与昵称校验；`real_id` 服务端生成；`is_admin=False`、隐私未确认；并发/大小写重复注册命中唯一约束时 400 且不覆盖已有账号；失败路径计入限流。
  - 登录：不存在邮箱、错误密码、不可用密码统一 401 `AUTH_FAILED`；凭据正确但停用 403；成功清除限流计数。
- `serializers.py`/`views.py`/`urls.py`：注册与登录入口（公开、强制匿名 CSRF、响应 `Cache-Control: private, no-store`），严格字段校验，拒绝 `is_admin` 等权限字段与未知字段；会话建立复用 `django.login()`（含会话键与 CSRF 轮换）。
- 管理命令：`grant_admin`、`revoke_admin`（按邮箱授予/撤销 `is_admin`，幂等，写审计）；`init_password`（新密码只经标准输入传入，经密码策略校验后哈希保存，写审计）。均支持可选 `--actor-email` 归属操作者。

### 2.2 审计（`backend/apps/audit/`）

- 新增动作 `admin_grant`、`admin_revoke`、`password_init`；`SYSTEM_MANAGED` 集合允许管理命令审计不带登录操作者（数据库约束兼容全空操作者）。

### 2.3 文档

- `backend/design_file/api.md`：注册/登录与管理命令状态更新为已交付；错误码表含 `RATE_LIMITED`（429）。

## 3. 测试结果

| 范围 | 结果 |
| --- | --- |
| 新增 `tests/accounts/test_auth.py`（16 项） | 全部通过：真实顺序 CSRF→注册→退出→登录→本人资料、匿名 CSRF 拒绝、域名严格校验、大小写重复不覆盖、模拟并发唯一约束异常路径、密码策略、权限字段拒绝、响应无内部标识、错误凭据统一口径、停用 403、邮箱/IP 限流与恢复及成功清零、键仅保存摘要、管理命令授予/撤销/幂等/审计、stdin 初始化密码 |
| 共享回归 `tests` 全量 | **234 项全部通过**（基线 218 + 新增 16） |
| 系统检查、迁移差异检查 | 通过、无差异 |
| 真实 HTTP 主流程（开发配置、独立端口） | 通过：CSRF 获取 → 注册 201（is_admin=false、privacy=false）→ /me 200 → 登出 200 → /me 401 → 登录 200 → /me 200 → 错误密码 401 `AUTH_FAILED` |
| 真实 HTTP 管理员配置 | 通过：注册账号 → `grant_admin` → 会话内 `/me` is_admin=true → `revoke_admin` → 同一会话 `/me` is_admin=false；审计 `admin_grant`/`admin_revoke` 落库 |

说明：测试专用快速哈希仅在 `config.settings.test` 启用，不用于正常服务进程；开发登录入口仍受 `DEBUG` 与 `ALLOW_DEV_LOGIN` 双开关控制，正式验收以注册登录链路为准。

## 4. 完成情况与剩余事项

- 阶段 2 通过条件达成：真实 HTTP 注册登录主链路可用；管理员授予/撤销可验证且旧会话即时反映撤权（管理员操作级拒绝随阶段 3 公告接口一并验证）；账号回归与全量回归通过。
- 剩余事项：阶段 3 公告 HTTP 层与治理通知、停用业务邮件排队；旧会话撤权后管理员写操作的 403 拒绝在阶段 3 公告用例中覆盖。

## 5. 交接

注册登录与限流参数均按阶段 1 冻结契约实现，后续调整须先更新 `api.md` 与《修订说明与待确认事项》；`auth_failure` 表为限流专用，勿用于业务查询。
