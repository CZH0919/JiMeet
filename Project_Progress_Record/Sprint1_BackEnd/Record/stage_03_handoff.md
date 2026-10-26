# Sprint1 后端中期交接手册

日期：2026-10-26｜阶段 1～3：czh｜阶段 4～6：zf

## 1. 接手基线

本次交付可发布、浏览、投递、查询及受控下载的后端。功能基线提交：`cba7558655eb392d1e55822ec5344e681bec4284`；本手册在该功能提交之后补充，不改变业务实现。已核验的规划 `Project_Progress_Record/Sprint1_BackEnd/Plan/sprint1_backend_plan.md` 保持不变。接口字段、权限及错误码唯一正文为 `backend/design_file/api.md`。

| 项目 | 值 |
| --- | --- |
| 工作分支 | `feat/sprint1-backend-recruitment-czh` |
| GitHub | `git@github.com:CZH0919/JiMeet.git`，当前仓库远端名 `github` |
| 同济 GitLab | `ssh://git@git.tongji.edu.cn:10022/tokendance/jimeet.git`，当前仓库远端名 `origin` |
| 版本状态 | 工作分支交付，尚不代表已评审或已合并 main；两个远端保存相同提交历史 |
| 数据库 / 依赖变化 | 无新增模型、迁移或运行时依赖，沿用原有迁移 |
| 配置修正 | `PRIVATE_FILE_ROOT` 未设置或为空时均使用 `backend/var/private`；该目录不提供静态 URL |

zf 接手前先核对实际远端地址，读取分支并核验功能提交已包含在其中：

```bash
git status --short --branch
git remote -v
git fetch origin
git log -3 --oneline origin/feat/sprint1-backend-recruitment-czh
git merge-base --is-ancestor cba7558655eb392d1e55822ec5344e681bec4284 origin/feat/sprint1-backend-recruitment-czh
```

最后一条退出码应为 0。完成代码评审与下文复现后，若尚未合入 main，可从该远端分支最新提交创建 `feat/sprint1-backend-applications-zf`，将本手册一并带入；若已经合入 main，则从包含本次功能的最新 main 创建。不要直接改写 czh 分支历史。使用明确的远端和分支推送，合并走团队 PR/MR 评审；两个平台的评审记录不会随 Git 推送同步。

## 2. 已交付与待完成

全部路径前缀为 `/api/v1`，无末尾斜杠。

| 状态 | 接口 / 能力 |
| --- | --- |
| 已实现：身份与基础 | `GET /healthz`、`GET /auth/csrf`、`POST /auth/dev-login`、`POST /auth/logout`、`GET/PATCH /me`、`POST /me/privacy-consent` |
| 已实现：招募 | `GET /tags`、`GET/POST /recruitments`、`GET/PATCH/DELETE /recruitments/{id}`、`POST /recruitments/{id}/close`、`GET /me/recruitments` |
| 已实现：申请入口 | `POST/GET /recruitments/{id}/applications`、`GET /me/applications`、`GET /applications/{id}`、`GET /applications/{id}/resume` |
| 阶段 4 待实现 | `PATCH /applications/{id}`；`POST /applications/{id}/{action}`，action 为 `withdraw/accept/reject/hold/unhold/read`，共 7 个方法/路径 |
| 阶段 5 待实现 | `GET /notifications`、`GET /notifications/unread-count`、`POST /notifications/{id}/read`、`POST /notifications/read-all` |
| 本轮保留占位 | SSO 两个 GET 接口返回 501；真实邮件发送、留存清理、孤立文件和审计清理命令仍为 reserved |

共 20 个已实现、11 个待实现方法/路径及 2 个 SSO 占位。当前 `PATCH /applications/{id}` 返回 405，其余未注册的后续路径返回 404。业务权限字段表达当前身份和状态的操作条件，不代表阶段 4 方法已上线。前端可开始招募、申请提交、历史与详情、简历下载的开发；处理按钮须等待相应接口交付。

## 3. 代码入口与不可破坏的约束

| 位置（相对项目根目录） | 职责与接续要点 |
| --- | --- |
| `backend/apps/core/views.py`、`serializers.py` | `PrivateAPIView`、`validate_data` 统一严格输入和私有缓存；默认保留 Session/CSRF。申请上传仅接收 multipart，新增 JSON 动作应使用相应解析器。 |
| `backend/apps/applications/services.py` | `submit_application`：身份/隐私预检 → 事务外暂存 → 招募状态补执行 → 招募锁内复核窗口与重复投递 → 原子创建申请和发布者通知。 |
| `backend/apps/applications/selectors.py`、`serializers.py` | 归属与留存过滤、有效状态投影、字段白名单；列表在分页前过滤，关联对象批量加载。序列化器只接收已鉴权、已投影的快照。 |
| `backend/apps/applications/policies.py` | 对象访问、投递、修改/撤回、处理规则。管理员无额外申请或简历读取权限。 |
| `backend/apps/files/services.py`、`views.py` | `download_resume` 在招募锁 → 申请锁下复核权限、打开文件并记录发布者读取审计，提交后传输；失败关闭句柄。 |
| `backend/apps/files/storage.py`、`validators.py` | 校验 PDF/DOC/DOCX、10 MiB 上限与文件特征，生成随机私有路径；`staged_resume` 在业务失败时清理新文件。 |
| `backend/apps/recruitments/services.py`、`state.py`、`rules.py` | 招募变更、`run_in_recruitment_tx`、`mark_full`、截止与七天处理规则；阶段 4 必须复用。 |
| `backend/apps/notifications/service.py`、`types.py`、`templates.py` | 通知与业务同事务；邮件日志已生成但真实发送未实现。提交后派发采用稳健回调，异常不能误触发文件回滚清理。 |
| `backend/apps/audit/service.py`、`core/exception_handler.py` | 业务审计和权限拒绝审计；原因不得包含简历内容、文件名、补充说明或凭据。 |
| `backend/config/urls.py` | 集中挂载业务路由；申请变更方法在对应应用接续。 |

关键约束：

1. 写既有招募/申请时不得在 `run_in_recruitment_tx` 外再套大事务；到期补执行独立提交，业务失败只回滚后续业务事务。锁顺序固定为招募 → 申请，同招募批量申请按主键排序，不额外锁关联用户行。
2. 接受申请后人数达到上限时，直接用 `mark_full` 同次保存人数与 full 状态，不先单独保存满员人数；其余 processing 由既有工具自动拒绝。数据库约束不能替代锁内业务复核。
3. 修改简历时先暂存新文件，业务失败清理新文件；提交成功后才清理旧文件。数据库提交后的通知派发或旧文件删除失败，不应被当作数据库已回滚，也不能删除新文件。
4. 招募软删除使 processing/accepted 失效，保留首次决定时间与历史人数；withdrawn/invalid 双方均不能下载，发布者也不能读取说明及私有标记。已拒绝或招募已关闭本身不禁止下载。
5. 当前 GET 使用有效时间状态，不保存状态、不清除未读修改。到关闭后七天边界显示 rejected；180 天留存从关闭、满员、删除的最早时间计算，过期即隐藏明细和文件，不能依赖物理清理任务。
6. 招募修改/删除只通知 processing/accepted 的申请人，已撤回和已拒绝者不通知；管理员删除另通知发布者。提交申请仅通知发布者，通知不携带申请正文或简历内容。
7. 阶段 4 的 `POST /applications/{id}/read` 使用详情的 `seen_updated_at`；锁内版本一致才清除标记，仅确认不刷新内容版本。不得改成 GET 顺带清除，也不得清掉读取后发生的新修改。

## 4. 运行准备与共享回归

要求 Python 3.12+、PostgreSQL 15+；本次验证使用 Python 3.14.3、PostgreSQL 17.11，依赖锁定为 Django 6.1.2、DRF 3.18.3、psycopg 3.3.6，以 `backend/requirements/base.txt` 为准。文件安全回归需要测试环境支持创建符号链接。

数据库维护者为该开发环境准备专用角色、开发库和 `test_<开发库名>`；应用角色拥有这两个库，不需要超级用户或建库权限。两库均需 `pg_trgm`，现有迁移可创建该扩展，受限环境可由维护者预先启用。以下示例数据库名为 `jimeet`，对应测试库为 `test_jimeet`，按实际资源替换。

在项目根目录的 PowerShell 执行；已有可用项目 Python 环境时跳过前两行：

```powershell
python -m venv backend/.venv
. ./backend/.venv/Scripts/Activate.ps1
python -m pip install -r backend/requirements/base.txt
$env:DJANGO_SETTINGS_MODULE = 'config.settings.dev'
$env:DJANGO_DEBUG = 'true'
$env:ALLOW_DEV_LOGIN = 'true'
$env:DJANGO_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:DB_NAME = 'jimeet'
$env:DB_USER = 'jimeet_app'
$env:DB_HOST = Read-Host 'PostgreSQL 主机'
$env:DB_PORT = '5432'
$env:DB_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host '项目数据库密码' -AsSecureString)).Password
$env:ALLOWED_EMAIL_DOMAINS = 'tongji.edu.cn'
$env:PRIVATE_FILE_ROOT = ''
Set-Location backend
python manage.py check
python manage.py migrate --noinput
python manage.py seed_tags
python manage.py test tests --keepdb --noinput --settings=config.settings.test
python manage.py runserver
```

配置只读取进程环境，不自动加载 `.env`。另开终端须重新加载同一份配置；同一开发环境保持 `DJANGO_SECRET_KEY` 稳定，否则已有会话失效。生产环境须另按部署配置关闭开发登录，本手册只用于开发接续。

上述共享测试命令运行仓库既有的 173 项测试，不包含阶段专项验证；专项结果见阶段记录，主流程可按下一节独立复现。测试运行器使用独立测试库并清理测试记录，保留数据库结构；不要将其指向业务库。手工演示使用每轮独立的测试身份和招募，结束时软删除测试招募；需要完全重置演示数据时，仅重建专用演示库，不在共享库执行清空操作。

`python manage.py run_sync_recruitments` 可执行到期关闭与七天自动拒绝。它需要人工运行或由后续部署调度，启动开发服务器不会自动周期执行。其余 reserved 命令不作为本轮运行步骤。

## 5. 可复现的 HTTP 主流程

在后端页面或已配置同源代理的前端页面打开浏览器控制台，先载入 `backend/design_file/api.md` 第 3.2 节的 `api`、`devLogin`、`confirmPrivacyConsent` 函数。以下操作只创建合成测试身份；同一浏览器按顺序切换身份，登录后函数会重新获取 CSRF 令牌。

```javascript
const suffix = Date.now().toString();
const ownerId = `s1_owner_${suffix}`;
const applicantId = `s1_applicant_${suffix}`;
await devLogin(ownerId);
await api('/me', { method: 'PATCH', json: { email_notify_enabled: false } });
const tags = (await api('/tags')).items;
if (!tags.length) throw new Error('请先执行 seed_tags');
const recruitment = await api('/recruitments', {
  method: 'POST',
  json: {
    title: `中期交接验证 ${suffix}`, type: 'competition',
    description: '合成测试招募', tag_ids: [tags[0].id], max_headcount: 2,
    deadline: new Date(Date.now() + 86400000).toISOString(),
  },
});
await api('/auth/logout', { method: 'POST' });
await devLogin(applicantId);
await api('/me', { method: 'PATCH', json: { email_notify_enabled: false } });
// 仅模拟合成身份的主动确认；正式页面仍须展示告知并取得用户确认。
if (!window.confirm('确认以合成测试身份模拟隐私告知同意？')) throw new Error('未确认');
await confirmPrivacyConsent();

// 生成无个人信息的有效单页空白 PDF。
const objects = [
  '<< /Type /Catalog /Pages 2 0 R >>',
  '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Resources << >> >>',
];
let pdf = '%PDF-1.4\n';
const offsets = [0];
objects.forEach((object, index) => {
  offsets.push(pdf.length);
  pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
});
const xref = pdf.length;
pdf += 'xref\n0 4\n0000000000 65535 f \n';
pdf += offsets.slice(1).map(n => `${String(n).padStart(10, '0')} 00000 n \n`).join('');
pdf += `trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
const form = new FormData();
form.append('resume', new File([pdf], 'sprint1-sample.pdf', { type: 'application/pdf' }));
form.append('note', '合成说明：熟悉 Python。');
const uploaded = await fetch(`/api/v1/recruitments/${recruitment.id}/applications`, {
  method: 'POST', credentials: 'same-origin',
  headers: { 'X-CSRFToken': csrfToken }, body: form,
});
const payload = await uploaded.json();
if (uploaded.status !== 201 || payload.code !== 'OK') throw new Error(JSON.stringify(payload));
const application = payload.data;
console.log(await api('/me/applications'));
console.log(await api(`/applications/${application.id}`));
await api('/auth/logout', { method: 'POST' });
await devLogin(ownerId);
console.log(await api(`/recruitments/${recruitment.id}/applications`));
console.log(await api(`/applications/${application.id}`));
const downloaded = await fetch(`/api/v1/applications/${application.id}/resume`, { credentials: 'same-origin' });
if (!downloaded.ok || !downloaded.headers.get('Content-Type')?.includes('application/pdf')) {
  throw new Error(`下载失败：${downloaded.status}`);
}
const file = await downloaded.blob();
console.assert(file.size === application.resume.size, '文件大小应一致');
console.log({ recruitmentId: recruitment.id, applicationId: application.id, ownerId, applicantId });
```

检查点：申请人结果没有 `applicant.name`、`publisher_mark`、`has_unseen_update`；发布者结果包含姓名，详情含说明和简历元数据；列表不含说明或简历元数据。发布者下载产生 `resume_view` 审计，申请人下载本人文件不产生跨用户读取审计。

在本轮数据上继续核验：

| 操作 | 预期 |
| --- | --- |
| 申请人再次提交同一招募 | 409 `DUPLICATE_APPLICATION`，只保留原申请和原文件 |
| 未确认隐私的第三个测试身份提交 | 403 `PRIVACY_NOT_CONSENTED` |
| 第三个身份读取该申请、简历或发布者申请列表 | 404；经维护者设置为管理员后仍是 404 |
| 发布者删除仍开放的测试招募，再由双方查询申请 | 申请为 invalid，历史保留；双方下载为 403，发布者不再看到说明 |
| 省略 CSRF 请求头后进行已登录写请求 | 403；不能通过关闭 CSRF 解决联调问题 |

管理员测试身份仅由维护者设置，开发登录不允许请求 `is_admin`。完整敏感字段矩阵及到期边界以接口文档第 6、8 节为准。

## 6. zf 接续顺序与验收

| 阶段 | 接续工作 | 重点通过条件 |
| --- | --- | --- |
| 4：申请处理 | 在 applications 服务/视图/路由扩展接受、拒绝、暂留、取消暂留、修改、撤回、修改已阅确认；撤回重投继续复用现有 POST | 最后名额竞争不超员；重复/终态处理不重复通知；接受与撤回互斥；修改与已阅确认不丢未读；文件替换失败保留旧文件 |
| 5：关联与通知 | 在 notifications 补查询、序列化、视图、路由；联验招募与申请副作用、同步命令 | 列表/未读数/已读操作使用同一归属及留存范围；补执行幂等；关联目标仍受访问权限约束；不把邮件占位当作已发送 |
| 6：回归与前端交付 | 将必要场景整理为团队可重复执行的回归，维护接口状态和示例，提交 `Project_Progress_Record/Sprint1_BackEnd/Record/sprint1_delivery.md` | 真实 HTTP 全流程与权限、文件、并发、CSRF 均通过；前端可独立接入；区分已实现、占位和后续事项 |

接续前应复现本手册主流程并审阅阶段记录；契约变更须同步唯一接口文档并告知对接成员。完整登录/注册、正式认证、聊天、推荐、真实邮件发送、清理平台和正式部署继续保持本次范围边界。
