import type {
  AnnouncementTimeKind,
  ApplicationStatus,
  JobStatus,
  JobType,
  NotificationType,
  SubmissionStatus,
  UserRole,
} from './models';

/** 枚举 → 中文展示文案的唯一真源，UI 层禁止硬编码枚举中文名 */

export const JOB_TYPE_LABEL: Record<JobType, string> = {
  competition: '竞赛组队',
  activity: '活动招聘',
  internship: '实验室实习',
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

export const SUBMISSION_STATUS_LABEL: Record<SubmissionStatus, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已驳回',
};

export const ROLE_LABEL: Record<UserRole, string> = {
  student: '学生',
  teacher: '教师',
};

export const TIME_KIND_LABEL: Record<AnnouncementTimeKind, string> = {
  deadline: '报名截止',
  event: '活动时间',
};

export const NOTIFICATION_TYPE_LABEL: Record<NotificationType, string> = {
  application_submitted: '收到新申请',
  application_accepted: '申请已接受',
  application_rejected: '申请已拒绝',
  application_withdrawn: '申请已撤回',
  application_updated: '申请已修改',
  anonymous_withdrawal: '申请随注销撤回',
  recruitment_closed: '招聘已关闭',
  recruitment_updated: '招聘信息已更新',
  recruitment_deleted: '招聘已删除',
  announcement_admin_removed: '公告被下架',
  announcement_removed: '公告已删除',
  announcement_submission_approved: '投稿已通过',
  announcement_submission_rejected: '投稿已驳回',
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

export const SUBMISSION_STATUS_TONE: Record<SubmissionStatus, string> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
};

/** 招聘类型 → 语义色 token 名 */
export const JOB_TYPE_TONE: Record<JobType, string> = {
  competition: 'primary',
  activity: 'success',
  internship: 'warning',
};
