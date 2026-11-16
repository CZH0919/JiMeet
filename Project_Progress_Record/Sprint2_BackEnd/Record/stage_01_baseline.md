# Sprint2 后端阶段 1 记录：基线、需求与契约统一

日期：2026-11-14｜分工：zf 主导、czh 参与｜执行依据：[Sprint2 后端开发规划](../Plan/sprint2_backend_plan.md) 阶段 1｜状态：已完成

后续边界修正与补充验证见 [阶段 1～3 修正记录](stage_01_03_review_fixes.md)；本文保留原交付批次的测试结果。

## 1. 范围

核验共享分支基线并建立可复现回归；补齐需求稿两份待补充附文；在 `backend/design_file/api.md` 冻结本轮跨模块契约；固定工程参数；确定公告通知关联、申请状态追溯与历史人数修复的数据方案、迁移归属与验证方法。

## 2. 基线核验（实际结果）

- 分支与版本：`backend_sprint2` @ `90ef949`，与规划记载的功能代码基线一致；工作区无未提交业务改动。
- 独立测试库应用全部 26 个迁移（含 `announcements.0001_initial`、`recruitments.0002_trigram_indexes` 与 `pg_trgm`）后：
  - `manage.py check --settings=config.settings.test`：0 问题；
  - `manage.py makemigrations --check --dry-run`：无差异；
  - 共享回归 `manage.py test tests --keepdb --noinput --settings=config.settings.test`：**218 个测试全部通过**。
- 基线异常及修复：首轮回归 218 个测试中 2 个报 `PermissionError`。原因：`config/settings/test.py` 的测试私有文件目录为固定共享路径，同一主机多开发账号的残留目录互相阻塞。修复为按系统用户名隔离该目录（`config/settings/test.py`），不改测试语义；修复后全部通过。该缺陷属测试基础设施隔离问题，与业务代码无关。

## 3. 核心修改

### 3.1 需求附文（`file/tasks/`）

- 新增 `需求验收测试用例.md`：按 FR-01～FR-11 给出可执行验收用例（AT-xx-xx），其中注册登录（AT-01-01～16）、权限与管理员撤权（AT-02-01～06）、简历本人读取与禁读（AT-04-01～08）、公告与治理（AT-09-01～15、AT-11-01～05）按本轮确认规则细化；与规划 §5 验收矩阵互为补充。
- 新增 `修订说明与待确认事项.md`：登记 2.0 修订稿规则变化与本轮补充约定的落实口径；固定全部设计授权参数（见第 4 节）；登记 P-01～P-10 事项清单，区分已定规则、待实施及后续范围。
- `软件需求规格说明2.0修订稿.md`：回填 1.5、3.4 的附文引用并补修订记录，其余正文未改动。

### 3.2 接口契约（`backend/design_file/api.md`）

- 新增 4.3/4.4：`POST /auth/register`、`POST /auth/login` 的字段、错误码与行为契约；`RATE_LIMITED`（429）入错误码表；`AUTH_FAILED` 明确登录失败统一口径。
- 公告（第 8 章）由草案改为冻结契约：字段约束、`created_at DESC, id DESC` 排序、只读 `is_pinned`、本人删除与治理删除分入口（`DELETE /announcements/{id}` / `DELETE /admin/announcements/{id}`）、`permissions` 区分两种删除入口、`recruitment_available`、锁内复核与重复删除口径。
- 通知（第 7 章）：新增 `announcement_id` 可空关联与 `announcement_admin_removed` 类型、目标关联互斥/一致性规则、邮件兼容策略（不再创建 `EmailLog(PENDING)`，`email_notify_enabled` 降级为兼容字段）。
- 历史记录与留存（6.1、9.1）：按 3.5 需求改为“不设固定 180 天隐藏”目标口径，标注既有截断于阶段 4/5 移除的实施状态。
- 招聘（5.2、5.4）：`max_headcount` 目标 1～200（阶段 4 实施，当前实现 50）；`DELETE /recruitments/{id}` 收敛为本人删除语义，新增治理删除入口 `DELETE /admin/recruitments/{id}`（阶段 4）。
- 概览（第 1 章）：9 个新增方法/路径按阶段标注，交付前不可调用；登记受控账号管理命令约定。

### 3.3 数据方案（`backend/design_file/design_manuscript/database.md` 新增第 4 章）

| 变更 | 迁移归属 | 验证方法 |
| --- | --- | --- |
| `notification.announcement_id` 可空关联 + 互斥/一致性 CHECK | zf，阶段 3，`notifications.0002` | 空库/存量库迁移、约束正反测试、旧通知兼容 |
| `auth_failure` 失败计数表（摘要键、INSERT 计数） | zf，阶段 2，`accounts.0002` | 并发计数一致、窗口恢复、成功清零 |
| `application_status_history` 状态变更历史 | czh，阶段 4，`applications.0002` | 各流转写史、并发一致、证据边界标注 |
| 历史已删除招聘 `accepted_count` 归零修复 | czh，阶段 4 | 修复前后对比、幂等、不重开招聘 |

## 4. 固定的工程参数（详见《修订说明与待确认事项》二）

密码策略（Django 验证器，8～128 字符）；失败限流（600 秒窗口、邮箱键 5 次、IP 键 20 次、429、成功清零、落库计数）；注册字段与内部标识生成规则；公告字段长度（title 1~100、content 1~5000、link_url ≤500、reason 1~500）与 `event_at` 不限未来时间；招聘文本参数（description 1~5000、note ≤1000）与 19 个预设标签候选；`RATE_LIMITED` 错误码。

## 5. 完成情况与剩余事项

- 阶段 1 通过条件达成：基线可复现（218/218 通过，失败项有结论并修复）；契约与数据方案可直接用于实施；需求稿、本轮补充约定与附文不再相互矛盾。
- 剩余事项（按阶段）：阶段 2 注册登录与管理命令实施；阶段 3 公告 HTTP 层、治理通知与停用业务邮件排队；阶段 4/5 招聘申请规则、180 天截断移除与通知矩阵复核（czh）；P-01～P-10 事项状态见附文三。

## 6. 交接

阶段 2 以本记录冻结的契约与参数实施注册登录：错误口径、限流参数与数据表按 3.2/3.3 执行，不再另行设定；变更契约须先同步 `api.md` 与《修订说明与待确认事项》。
