import type { ApplicationStatus, JobStatus, JobType, NotificationType, UserRole } from './models';

/** 枚举 → 中文展示文案的唯一真源，UI 层禁止硬编码枚举中文名 */

export const JOB_TYPE_LABEL: Record<JobType, string> = {
  competition: '竞赛组队',
  campus_activity: '活动招聘',
};

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  open: '进行中',
  full: '已满员',
  closed: '已关闭',
};

export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  pending: '处理中',
  accepted: '已接受',
  rejected: '已拒绝',
  withdrawn: '已撤回',
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
  application_accepted: '申请处理结果',
  application_rejected: '申请处理结果',
  application_withdrawn: '申请撤回通知',
  job_removed_by_admin: '招聘删除通知',
  job_modified: '招聘修改通知',
  job_closed: '招聘状态变更',
};

/** 相关领域候选值（发布页下拉 + 筛选面板共用） */
export const FIELDS = ['计算机', '设创', '商学', '工程', '电气', '自动化', '机械', '人工智能'];

/** 状态 → 语义色 token 名（供 StatusBadge 使用） */
export const JOB_STATUS_TONE: Record<JobStatus, string> = {
  open: 'primary',
  full: 'warning',
  closed: 'muted',
};

export const APPLICATION_STATUS_TONE: Record<ApplicationStatus, string> = {
  pending: 'primary',
  accepted: 'success',
  rejected: 'danger',
  withdrawn: 'muted',
};
