import type { ApplicationStatus, JobStatus, JobType, NotificationType, UserRole } from './models';

/** 枚举 → 中文展示文案的唯一真源，UI 层禁止硬编码枚举中文名 */

export const JOB_TYPE_LABEL: Record<JobType, string> = {
  competition: '竞赛组队',
  activity: '活动招聘',
  internship: '实验室实习',
  competition_notice: '竞赛通知',
};

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  open: '进行中',
  full: '已满员',
  closed: '已关闭',
};

export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  processing: '处理中',
  accepted: '已接受',
  rejected: '已拒绝',
  withdrawn: '已撤回',
  invalid: '已失效',
};

export const ROLE_LABEL: Record<UserRole, string> = {
  student: '学生',
  teacher: '教师',
};

export const MARK_ACTION_LABEL: Record<'accept' | 'hold' | 'reject', string> = {
  accept: '确认',
  hold: '暂留',
  reject: '拒绝',
};

export const NOTIFICATION_TYPE_LABEL: Record<NotificationType, string> = {
  application_submitted: '申请投递通知',
  application_accepted: '申请已接受',
  application_rejected: '申请已拒绝',
  application_withdrawn: '申请已撤回',
  application_updated: '申请已修改',
  recruitment_closed: '招聘已关闭',
  recruitment_updated: '招聘信息已更新',
  recruitment_deleted: '招聘已删除',
  admin_removed: '内容被管理员删除',
};

/** 状态 → 语义色 token 名（供 StatusBadge 使用） */
export const JOB_STATUS_TONE: Record<JobStatus, string> = {
  open: 'primary',
  full: 'warning',
  closed: 'muted',
};

export const APPLICATION_STATUS_TONE: Record<ApplicationStatus, string> = {
  processing: 'primary',
  accepted: 'success',
  rejected: 'danger',
  withdrawn: 'muted',
  invalid: 'muted',
};
