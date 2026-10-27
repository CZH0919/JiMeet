import type { JobType } from './models';

/** 校验规则（对应 SRS FR-04/FR-05），纯函数、无 IO，可直接单测 */

export interface CreateJobInput {
  type: JobType;
  title: string;
  description: string;
  requirement: string;
  field: string;
  recruitCount: number;
  deadline: string;
}

export type FieldErrors<T> = Partial<Record<keyof T | 'form', string>>;

const ACCEPTED_EXT = ['.pdf', '.doc', '.docx'];
export const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

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
  if (!ACCEPTED_EXT.includes(extOf(file.name))) {
    return '仅支持 PDF / DOC / DOCX 格式';
  }
  if (file.size > MAX_FILE_SIZE) {
    return '文件不得超过 10 MB';
  }
  return null;
}

export function validateNote(note: string): string | null {
  if (note.trim().length > 500) return '补充说明不超过 500 字';
  return null;
}

/** 发布 / 编辑招聘表单校验 */
export function validateJobForm(input: CreateJobInput): FieldErrors<CreateJobInput> {
  const errors: FieldErrors<CreateJobInput> = {};

  if (!input.title || !input.title.trim()) errors.title = '请输入名称';
  else if (input.title.trim().length < 2) errors.title = '名称至少 2 个字';
  else if (input.title.trim().length > 60) errors.title = '名称不超过 60 字';

  if (!input.description || !input.description.trim()) errors.description = '请描述需求';
  else if (input.description.trim().length < 10) errors.description = '需求描述至少 10 字';
  else if (input.description.trim().length > 2000) errors.description = '需求描述不超过 2000 字';

  if (input.requirement.trim().length > 1000) errors.requirement = '补充说明不超过 1000 字';

  if (!input.field) errors.field = '请选择相关领域';

  if (!Number.isInteger(input.recruitCount) || input.recruitCount < 1)
    errors.recruitCount = '计划招募人数至少为 1';
  else if (input.recruitCount > 50) errors.recruitCount = '计划招募人数不超过 50 人';

  if (!input.deadline) errors.deadline = '请选择截止时间';
  else if (new Date(input.deadline).getTime() <= Date.now())
    errors.deadline = '截止时间须晚于当前时间';

  return errors;
}

/** 管理员治理删除：原因必填且 ≥10 字 */
export function validateModerationReason(reason: string): string | null {
  if (!reason.trim()) return '请填写删除原因';
  if (reason.trim().length < 10) return '删除原因至少 10 字';
  return null;
}

export function validateLoginEmail(email: string): string | null {
  if (!email.trim()) return '请输入邮箱';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return '邮箱格式不正确';
  return null;
}

export function validateLoginPassword(pwd: string): string | null {
  if (!pwd) return '请输入密码';
  return null;
}
