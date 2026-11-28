import type { AnnouncementTimeKind, JobType, Tag, UserRole } from './models';

/** 校验规则（对应后端接口契约），纯函数、无 IO，可直接单测 */

export interface CreateJobInput {
  type: JobType;
  title: string;
  description: string;
  note: string;
  tags: Tag[];
  minHeadcount: number | null;
  maxHeadcount: number | null;
  deadline: string;
}

export interface AnnouncementInput {
  title: string;
  content: string;
  timeKind: AnnouncementTimeKind;
  eventAt: string;
  linkUrl: string;
  recruitmentId: number | null;
}

/** 普通用户投稿：不能关联招聘，其余字段与公告一致 */
export type SubmissionInput = Omit<AnnouncementInput, 'recruitmentId'>;

/** 登录：password 与 code 恰好提供一种（后端二选一） */
export interface LoginInput {
  email: string;
  password?: string;
  code?: string;
}

/** 注册：邮箱验证码通过后提交密码与身份资料 */
export interface RegisterInput {
  email: string;
  password: string;
  passwordConfirm: string;
  name: string;
  nickname: string;
  role: UserRole;
}

export type FieldErrors<T> = Partial<Record<keyof T | 'form', string>>;

const ACCEPTED_EXT = ['.pdf', '.doc', '.docx'];
export const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MiB
export const MAX_DEADLINE_AHEAD_MS = 365 * 24 * 60 * 60 * 1000; // 截止时间不得晚于当前时间一年

export const LIMITS = {
  jobTitle: 100,
  jobDescription: 5000,
  headcount: 200,
  note: 1000,
  announcementTitle: 100,
  announcementContent: 5000,
  linkUrl: 500,
  reason: 500,
  message: 500,
  nickname: 32,
  name: 32,
  nameMin: 1,
  passwordMin: 8,
  passwordMax: 128,
  codeLength: 6,
  accountIdMax: 64,
} as const;

/** 注册验证码 / 登录验证码的有效期与重发间隔（秒）：以接口返回值为准，此处仅作文案兜底 */
export const CODE_TTL_SECONDS = 300;
export const CODE_RESEND_SECONDS = 60;

export function extOf(name: string): string {
  const i = name.lastIndexOf('.');
  return i >= 0 ? name.slice(i).toLowerCase() : '';
}

export function fileSizeLabel(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

/** 简历文件：格式 / 大小即时校验（选择瞬间调用，不等待提交） */
export function validateResumeFile(file: File): string | null {
  if (!ACCEPTED_EXT.includes(extOf(file.name))) return '仅支持 PDF / DOC / DOCX 格式';
  if (file.size === 0) return '文件不能为空';
  if (file.size > MAX_FILE_SIZE) return '文件不得超过 10 MB';
  return null;
}

export function validateNote(note: string): string | null {
  if (note.trim().length > LIMITS.note) return `补充说明不超过 ${LIMITS.note} 字`;
  return null;
}

/** 聊天正文：纯文本，按 Unicode 码点计数，1～500 */
export function messageLength(text: string): number {
  return Array.from(text).length;
}

export function validateMessage(text: string): string | null {
  if (!text.trim()) return '消息不能为空';
  if (messageLength(text) > LIMITS.message) return `单条消息不超过 ${LIMITS.message} 个字符`;
  return null;
}

/** 发布 / 编辑招聘表单校验 */
export function validateJobForm(input: CreateJobInput): FieldErrors<CreateJobInput> {
  const errors: FieldErrors<CreateJobInput> = {};

  const title = input.title.trim();
  if (!title) errors.title = '请输入招聘名称';
  else if (title.length > LIMITS.jobTitle) errors.title = `名称不超过 ${LIMITS.jobTitle} 字`;

  const desc = input.description.trim();
  if (!desc) errors.description = '请填写需求描述';
  else if (desc.length > LIMITS.jobDescription)
    errors.description = `需求描述不超过 ${LIMITS.jobDescription} 字`;

  if (input.note.trim().length > LIMITS.note) errors.note = `补充说明不超过 ${LIMITS.note} 字`;

  if (!input.tags || input.tags.length === 0) errors.tags = '请至少选择一个相关标签';

  if (input.maxHeadcount == null) {
    errors.maxHeadcount = '请输入计划招募人数';
  } else if (!Number.isInteger(input.maxHeadcount) || input.maxHeadcount < 1) {
    errors.maxHeadcount = '计划招募人数至少为 1';
  } else if (input.maxHeadcount > LIMITS.headcount) {
    errors.maxHeadcount = `计划招募人数不超过 ${LIMITS.headcount} 人`;
  }

  if (input.minHeadcount != null) {
    if (!Number.isInteger(input.minHeadcount) || input.minHeadcount < 1) {
      errors.minHeadcount = '人数下限至少为 1';
    } else if (input.maxHeadcount != null && input.minHeadcount > input.maxHeadcount) {
      errors.minHeadcount = '人数下限不能大于上限';
    }
  }

  if (!input.deadline) errors.deadline = '请选择截止时间';
  else if (new Date(input.deadline).getTime() <= Date.now()) errors.deadline = '截止时间须晚于当前时间';
  else if (new Date(input.deadline).getTime() > Date.now() + MAX_DEADLINE_AHEAD_MS)
    errors.deadline = '截止时间不能晚于当前时间一年';

  return errors;
}

function validateAnnouncementFields(input: AnnouncementInput | SubmissionInput): FieldErrors<AnnouncementInput> {
  const errors: FieldErrors<AnnouncementInput> = {};

  const title = input.title.trim();
  if (!title) errors.title = '请输入公告标题';
  else if (title.length > LIMITS.announcementTitle)
    errors.title = `标题不超过 ${LIMITS.announcementTitle} 字`;

  const content = input.content.trim();
  if (!content) errors.content = '请填写公告内容';
  else if (content.length > LIMITS.announcementContent)
    errors.content = `内容不超过 ${LIMITS.announcementContent} 字`;

  if (!input.timeKind) errors.timeKind = '请选择时间类型';
  if (!input.eventAt) errors.eventAt = '请选择时间';

  const link = input.linkUrl.trim();
  if (link) {
    if (link.length > LIMITS.linkUrl) errors.linkUrl = `链接不超过 ${LIMITS.linkUrl} 字`;
    else if (!/^https?:\/\//i.test(link)) errors.linkUrl = '仅支持 http:// 或 https:// 开头的地址';
  }

  return errors;
}

/** 公告发布表单校验 */
export function validateAnnouncementForm(input: AnnouncementInput): FieldErrors<AnnouncementInput> {
  const errors = validateAnnouncementFields(input);
  if (input.recruitmentId != null && (!Number.isInteger(input.recruitmentId) || input.recruitmentId <= 0)) {
    errors.recruitmentId = '关联招聘 ID 不合法';
  }
  return errors;
}

/** 普通用户投稿表单校验（不能关联招聘） */
export function validateSubmissionForm(input: SubmissionInput): FieldErrors<SubmissionInput> {
  return validateAnnouncementFields(input) as FieldErrors<SubmissionInput>;
}

/** 管理员治理删除：原因必填，1～500 字 */
export function validateModerationReason(reason: string): string | null {
  const text = reason.trim();
  if (!text) return '请填写删除原因';
  if (text.length > LIMITS.reason) return `删除原因不超过 ${LIMITS.reason} 字`;
  return null;
}

/** 公告投稿驳回：理由必填，1～500 字 */
export function validateRejectReason(reason: string): string | null {
  const text = reason.trim();
  if (!text) return '请填写驳回理由';
  if (text.length > LIMITS.reason) return `驳回理由不超过 ${LIMITS.reason} 字`;
  return null;
}

/**
 * 账号只填邮箱前缀，@tongji.edu.cn 为固定后缀。
 * 后端以完整邮箱为准（域名精确等于 tongji.edu.cn），这里只挡住明显非法输入，
 * 不按邮箱前缀字符集或长度额外收紧，避免误伤学校真实账号。
 */
export const EMAIL_SUFFIX = '@tongji.edu.cn';

/** 允许用户误粘贴完整邮箱：只取 @ 前面的部分 */
export function normalizeAccountId(raw: string): string {
  const value = raw.trim();
  const at = value.indexOf('@');
  return (at >= 0 ? value.slice(0, at) : value).trim();
}

export function toTongjiEmail(raw: string): string {
  return `${normalizeAccountId(raw)}${EMAIL_SUFFIX}`;
}

export function validateAccountId(raw: string): string | null {
  const value = normalizeAccountId(raw);
  if (!value) return '请输入邮箱前缀';
  if (value.length > LIMITS.accountIdMax) return `邮箱前缀不超过 ${LIMITS.accountIdMax} 位`;
  if (/\s/.test(value)) return '邮箱前缀不能包含空格';
  if (value.startsWith('.') || value.endsWith('.')) return '邮箱前缀不能以点开头或结尾';
  if (/[^A-Za-z0-9._%+-]/.test(value)) return '邮箱前缀只能包含字母、数字或 . _ % + -';
  return null;
}

/** 邮箱验证码：6 位数字字符串，保留前导零 */
export function validateCode(raw: string): string | null {
  const value = raw.trim();
  if (!value) return '请输入验证码';
  if (value.length !== LIMITS.codeLength) return `验证码为 ${LIMITS.codeLength} 位数字`;
  if (!/^\d+$/.test(value)) return `验证码为 ${LIMITS.codeLength} 位数字`;
  return null;
}

/** 姓名暂无法与教务系统核验，至少挡住纯数字、纯符号这类明显占位的填写 */
export function validateName(raw: string): string | null {
  const value = raw.trim();
  if (!value) return '请输入姓名';
  if (value.length < LIMITS.nameMin) return `姓名至少 ${LIMITS.nameMin} 个字`;
  if (value.length > LIMITS.name) return `姓名不超过 ${LIMITS.name} 字`;
  if (/^[\d\s._\-+/\\|]+$/.test(value)) return '姓名不能只填数字或符号';
  return null;
}

/** 登录密码表单（仅供页面本地校验使用） */
export interface LoginPasswordForm {
  accountId: string;
  password: string;
}

/** 登录验证码表单 */
export interface LoginCodeForm {
  accountId: string;
  code: string;
}

/** 注册表单：验证码通过后再填密码与身份资料 */
export interface RegisterForm {
  accountId: string;
  code: string;
  password: string;
  confirm: string;
  name: string;
  nickname: string;
  role: UserRole;
}

export type LoginPasswordErrors = Partial<Record<keyof LoginPasswordForm, string>>;
export type LoginCodeErrors = Partial<Record<keyof LoginCodeForm, string>>;
export type RegisterErrors = Partial<Record<keyof RegisterForm, string>>;

/**
 * 密码提示文案：前端预校验与后端校验器（Django 密码验证器）共用同一套说法。
 * 后端返回的英文/中文原文会经 `canonicalPasswordMessage` 归一到这里的措辞，
 * 避免同一个问题出现「密码过于常见，请更换」和「参数校验失败（这个密码太常见了。）」两种提示。
 */
export const PASSWORD_MESSAGES = {
  required: '请输入密码',
  tooShort: `密码至少 ${LIMITS.passwordMin} 位`,
  tooLong: `密码不超过 ${LIMITS.passwordMax} 位`,
  allDigits: '密码不能全部为数字',
  tooCommon: '密码过于常见，请更换',
  containsAccount: '密码不能包含邮箱前缀',
  containsName: '密码不能包含姓名',
} as const;

/** 注册页密码输入框下方的规则说明，与 `validatePassword` 的判断顺序保持一致 */
export const PASSWORD_HINT = `至少 ${LIMITS.passwordMin} 位，不能全部为数字`;

/** 各字段的简短说明：只补充用户看不出来的信息，不复述标签本身 */
export const FIELD_HINT = {
  name: '仅用于发布者查看，不对其他用户公开',
  nickname: '留空则由系统生成「同学_」开头的昵称',
} as const;

const WEAK_PASSWORDS = new Set([
  '12345678',
  '123456789',
  '1234567890',
  'password',
  'password1',
  'qwertyui',
  'abc12345',
  'tongji123',
]);

export function validatePassword(password: string, context?: { email?: string; name?: string }): string | null {
  if (!password) return PASSWORD_MESSAGES.required;
  if (password.length < LIMITS.passwordMin) return PASSWORD_MESSAGES.tooShort;
  if (password.length > LIMITS.passwordMax) return PASSWORD_MESSAGES.tooLong;
  if (/^\d+$/.test(password)) return PASSWORD_MESSAGES.allDigits;
  if (WEAK_PASSWORDS.has(password.toLowerCase())) return PASSWORD_MESSAGES.tooCommon;

  const lower = password.toLowerCase();
  const emailLocal = context?.email?.split('@')[0]?.toLowerCase();
  if (emailLocal && emailLocal.length >= 4 && lower.includes(emailLocal)) {
    return PASSWORD_MESSAGES.containsAccount;
  }
  if (context?.name && context.name.length >= 2 && lower.includes(context.name.toLowerCase())) {
    return PASSWORD_MESSAGES.containsName;
  }
  return null;
}

/** 后端密码校验原文 → 前端统一文案（匹配不到时返回 null，交回调用方处理） */
const PASSWORD_TEXT_RULES: [RegExp, string][] = [
  [/太常见|常见密码|common|widely used/i, PASSWORD_MESSAGES.tooCommon],
  [/全是数字|全为数字|entirely numeric|numeric only/i, PASSWORD_MESSAGES.allDigits],
  [/太短|too short|至少 ?8|at least ?8/i, PASSWORD_MESSAGES.tooShort],
  [/太长|too long/i, PASSWORD_MESSAGES.tooLong],
  [/过于相似|too similar/i, PASSWORD_MESSAGES.containsAccount],
];

export function canonicalPasswordMessage(text: string): string | null {
  const raw = text.trim();
  if (!raw) return null;
  for (const [re, message] of PASSWORD_TEXT_RULES) {
    if (re.test(raw)) return message;
  }
  return null;
}

export function validateNickname(nickname: string): string | null {
  const value = nickname.trim();
  if (!value) return '昵称不能为空';
  if (value.length > LIMITS.nickname) return `昵称不超过 ${LIMITS.nickname} 字`;
  return null;
}
