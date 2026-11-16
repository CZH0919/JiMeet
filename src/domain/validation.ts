import type { AnnouncementTimeKind, JobType, Tag, UserRole } from './models';

/** 校验规则（对应后端接口契约），纯函数、无 IO，可直接单测 */

export interface CreateJobInput {
  type: JobType;
  title: string;
  description: string;
  tags: Tag[];
  minHeadcount: number | null;
  maxHeadcount: number;
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

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegisterInput extends LoginInput {
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
  nickname: 32,
  name: 32,
  passwordMin: 8,
  passwordMax: 128,
} as const;

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

  if (!input.tags || input.tags.length === 0) errors.tags = '请至少选择一个相关标签';

  if (!Number.isInteger(input.maxHeadcount) || input.maxHeadcount < 1) {
    errors.maxHeadcount = '计划招募人数至少为 1';
  } else if (input.maxHeadcount > LIMITS.headcount) {
    errors.maxHeadcount = `计划招募人数不超过 ${LIMITS.headcount} 人`;
  }

  if (input.minHeadcount != null) {
    if (!Number.isInteger(input.minHeadcount) || input.minHeadcount < 1) {
      errors.minHeadcount = '人数下限至少为 1';
    } else if (input.minHeadcount > input.maxHeadcount) {
      errors.minHeadcount = '人数下限不能大于上限';
    }
  }

  if (!input.deadline) errors.deadline = '请选择截止时间';
  else if (new Date(input.deadline).getTime() <= Date.now()) errors.deadline = '截止时间须晚于当前时间';
  else if (new Date(input.deadline).getTime() > Date.now() + MAX_DEADLINE_AHEAD_MS)
    errors.deadline = '截止时间不能晚于当前时间一年';

  return errors;
}

/** 公告发布 / 编辑表单校验 */
export function validateAnnouncementForm(input: AnnouncementInput): FieldErrors<AnnouncementInput> {
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

  if (input.recruitmentId != null && (!Number.isInteger(input.recruitmentId) || input.recruitmentId <= 0)) {
    errors.recruitmentId = '关联招聘 ID 不合法';
  }

  return errors;
}

/** 管理员治理删除：原因必填，1～500 字 */
export function validateModerationReason(reason: string): string | null {
  const text = reason.trim();
  if (!text) return '请填写删除原因';
  if (text.length > LIMITS.reason) return `删除原因不超过 ${LIMITS.reason} 字`;
  return null;
}

/** 账号只填学号/工号，@tongji.edu.cn 为固定后缀 */
export const EMAIL_SUFFIX = '@tongji.edu.cn';

const ACCOUNT_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$/;

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
  if (!value) return '请输入学号 / 工号';
  if (!ACCOUNT_ID_RE.test(value)) return '学号为 3–32 位字母、数字或 . _ -';
  return null;
}

/** 登录表单（只含学号与密码，提交前拼成邮箱） */
export interface AccountLoginForm {
  accountId: string;
  password: string;
}

/** 注册表单 */
export interface AccountRegisterForm extends AccountLoginForm {
  name: string;
  nickname: string;
  role: UserRole;
  confirm: string;
}

export type AccountLoginErrors = Partial<Record<keyof AccountLoginForm, string>>;
export type AccountRegisterErrors = Partial<Record<keyof AccountRegisterForm, string>>;

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
  if (!password) return '请输入密码';
  if (password.length < LIMITS.passwordMin) return `密码至少 ${LIMITS.passwordMin} 位`;
  if (password.length > LIMITS.passwordMax) return `密码不超过 ${LIMITS.passwordMax} 位`;
  if (/^\d+$/.test(password)) return '密码不能全部为数字';
  if (WEAK_PASSWORDS.has(password.toLowerCase())) return '密码过于常见，请更换';

  const lower = password.toLowerCase();
  const emailLocal = context?.email?.split('@')[0]?.toLowerCase();
  if (emailLocal && emailLocal.length >= 4 && lower.includes(emailLocal)) {
    return '密码不能与邮箱过于相似';
  }
  if (context?.name && context.name.length >= 2 && lower.includes(context.name.toLowerCase())) {
    return '密码不能与姓名过于相似';
  }
  return null;
}

export function validateNickname(nickname: string): string | null {
  const value = nickname.trim();
  if (!value) return '昵称不能为空';
  if (value.length > LIMITS.nickname) return `昵称不超过 ${LIMITS.nickname} 字`;
  return null;
}
