import type { Job, JobStatus, User } from './models';

/** 招聘状态机：open → full（满员）｜ open → closed（手动关闭 / 到期） */

export type ApplyDecision = { ok: true } | { ok: false; reason: string };

/**
 * 统一判定「能否申请」，结果同时驱动按钮可用性与 tooltip 文案，
 * 避免「按钮能点但提交报错」。
 */
export function canApply(job: Job, user: User | null): ApplyDecision {
  if (!user) return { ok: false, reason: '请先登录后再申请' };
  if (job.status !== 'open') return { ok: false, reason: '仅进行中状态可投递申请' };
  if (new Date(job.deadline).getTime() < Date.now())
    return { ok: false, reason: '该招聘已过截止时间' };
  if (user.role !== 'student') return { ok: false, reason: '仅学生可提交申请' };
  if (job.publisher.id === user.id) return { ok: false, reason: '不可申请本人发布的招聘' };
  if (job.myApplicationStatus)
    return { ok: false, reason: '你已申请过该招聘，不可重复申请' };
  return { ok: true };
}

/** 满员判定：已接受人数达到计划招募人数 */
export function isFull(job: Pick<Job, 'recruitCount' | 'acceptedCount'>): boolean {
  return job.acceptedCount >= job.recruitCount;
}

/** 已过截止时间 */
export function isExpired(job: Pick<Job, 'deadline'>): boolean {
  return new Date(job.deadline).getTime() < Date.now();
}

/** 由业务规则推导招聘「应处」状态（用于 mock 与展示兜底） */
export function deriveJobStatus(job: Pick<Job, 'status' | 'recruitCount' | 'acceptedCount' | 'deadline'>): JobStatus {
  if (job.status === 'closed') return 'closed';
  if (isFull(job)) return 'full';
  if (isExpired(job)) return 'closed';
  return 'open';
}

/** 截止时间剩余：返回天/小时（用于列表「剩余截止时间」） */
export function remainingTime(deadline: string): string {
  const ms = new Date(deadline).getTime() - Date.now();
  if (ms <= 0) return '已结束';
  const days = Math.floor(ms / 86_400_000);
  const hours = Math.floor((ms % 86_400_000) / 3_600_000);
  if (days > 0) return `${days}天${hours}小时`;
  return `${hours}小时`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
