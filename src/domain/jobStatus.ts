import type { Job, User } from './models';

/** 招聘状态机：open → full（满员）｜ open → closed（手动关闭 / 到期） */

export type ApplyDecision = { ok: true } | { ok: false; reason: string };

/** 后端错误码：未确认个人信息处理告知。属软阻塞——可在申请弹窗内完成确认，不应禁用申请入口。 */
export const PRIVACY_NOT_CONSENTED = 'PRIVACY_NOT_CONSENTED';

/** 已过截止时间 */
export function isExpired(job: Pick<Job, 'deadline'>): boolean {
  return new Date(job.deadline).getTime() < Date.now();
}

/**
 * 本地兜底判定「能否申请」，仅在拿不到后端 permissions 时使用；
 * 结果同时驱动按钮可用性与提示文案，避免「按钮能点但提交报错」。
 */
export function canApply(job: Job, user: User | null): ApplyDecision {
  if (!user) return { ok: false, reason: '请先登录后再申请' };
  if (job.status !== 'open') return { ok: false, reason: '仅进行中状态可投递申请' };
  if (isExpired(job)) return { ok: false, reason: '该招聘已过截止时间' };
  if (job.publisher.id === user.id) return { ok: false, reason: '不可申请本人发布的招聘' };
  if (!user.privacyConsented) return { ok: false, reason: '请先确认个人信息处理告知' };
  if (job.myApplicationStatus) return { ok: false, reason: '你已申请过该招聘，不可重复申请' };
  return { ok: true };
}
