/**
 * 前端页面使用的领域模型。
 * UI 层只认这里定义的字段，后端 snake_case、枚举、可空语义都在 data/http/mappers.ts 收口。
 */

export type UserRole = 'student' | 'teacher';

/** 公共用户：后端只暴露 uid / nickname / role，不含姓名、邮箱 */
export interface PublicUser {
  id: string; // 32 位十六进制 uid；已注销用户为 ''
  name: string; // 展示名（nickname）
  role: UserRole;
}

/** 本人资料（GET /me） */
export interface User {
  id: string;
  /** 展示名（昵称） */
  name: string;
  /** 姓名：仅本人资料可见，未做学校核验，不作授权依据 */
  realName?: string;
  role: UserRole;
  isAdmin: boolean;
  email?: string;
  privacyConsented: boolean;
  /** 兼容字段：不代表可用邮件功能，前端不作为开关展示 */
  emailNotifyEnabled: boolean;
}

/** 招聘类型（后端 competition / activity；internship 仅用于历史记录展示） */
export type JobType = 'competition' | 'activity' | 'internship';

/** 招聘业务状态：进行中 / 已满员 / 已关闭 */
export type JobStatus = 'open' | 'full' | 'closed';

export interface Tag {
  id: number;
  name: string;
}

/** 招募详情 permissions：仅用于按钮展示，写请求仍由服务端重新校验 */
export interface JobPermissions {
  canApply: boolean;
  canEdit: boolean;
  canClose: boolean;
  /** 本人删除入口（发布者身份） */
  canDelete: boolean;
  /** 管理员治理删除入口（独立入口） */
  canGovernDelete: boolean;
  canViewApplications: boolean;
  /** 后端错误码转成的展示文案（可空） */
  applyBlockedReason: string | null;
  /** 后端原始业务错误码（可空），用于区分「隐私告知未确认」这类软阻塞 */
  applyBlockedCode: string | null;
}

export interface Job {
  id: string;
  type: JobType;
  title: string;
  description: string;
  /** 发布者的招聘补充说明（与申请附带的说明是两回事） */
  note: string | null;
  tags: Tag[];
  minHeadcount: number | null;
  maxHeadcount: number;
  acceptedCount: number;
  /** ISO 8601（带时区） */
  deadline: string;
  status: JobStatus;
  isDeleted: boolean;
  publisher: PublicUser;
  createdAt: string;
  updatedAt: string;
  /** 详情接口返回的最近一次申请状态；列表为 undefined */
  myApplicationStatus?: ApplicationStatus | null;
  /** 详情接口对发布者返回的申请总数 */
  applicationCount: number;
  /** 详情接口对发布者返回的五种状态计数（仅发布者可见） */
  applicationCounts?: Partial<Record<ApplicationStatus, number>>;
  permissions?: JobPermissions;
}

/** 申请状态：除 processing 外均为终态 */
export type ApplicationStatus = 'processing' | 'accepted' | 'rejected' | 'withdrawn' | 'invalid';

export interface ResumeFile {
  fileName: string;
  size: number; // 字节
  type: string; // pdf | doc | docx
}

/** 申请中的招募引用：招募被删除后仍用于申请历史展示 */
export interface RecruitmentReference {
  id: string;
  title: string;
  type: JobType;
  status: JobStatus;
  isDeleted: boolean;
  deletedAt: string | null;
}

export interface Application {
  id: string;
  jobId: string;
  jobTitle: string;
  jobType: JobType;
  /** 招募当前是否已删除（申请记录仍保留） */
  jobDeleted: boolean;
  applicant: PublicUser;
  /** null 表示后端未返回简历元数据（无权限/不可见） */
  resume: ResumeFile | null;
  note?: string;
  status: ApplicationStatus;
  createdAt: string;
  updatedAt: string;
  decidedAt: string | null;
  /** 发布者私有标记：hold 表示暂留（申请仍为 processing） */
  publisherMark: 'none' | 'hold';
  /** 申请人修改过申请，发布者查看前显示「已修改」红点 */
  modified: boolean;
  canModify: boolean;
  canWithdraw: boolean;
  canProcess: boolean;
  canDownloadResume: boolean;
}

/** 聊天消息：发送方/接收方均为公开 uid；readAt 仅本人视角的对方消息有意义 */
export interface Message {
  id: string;
  conversationId: string;
  senderId: string;
  recipientId: string;
  text: string;
  createdAt: string;
  readAt: string | null;
}

export interface Conversation {
  id: string;
  peer: PublicUser;
  lastMessage: Pick<Message, 'text' | 'createdAt' | 'senderId'> | null;
  /** 本人未读的对方消息数 */
  unreadCount: number;
  updatedAt: string;
}

/** 对方主页（GET /users/{uid}）：只含公开资料与聊天入口 */
export interface PeerProfile {
  uid: string;
  nickname: string;
  role: UserRole;
  canChat: boolean;
  /** 已有会话编号（可空）；打开主页不会创建会话 */
  conversationId: string | null;
}

/** 公告时间类型：报名截止时间 / 活动时间 */
export type AnnouncementTimeKind = 'deadline' | 'event';

export interface AnnouncementPermissions {
  /** 公告不可编辑，后端恒为 false */
  canEdit: boolean;
  canDelete: boolean;
  canGovernDelete: boolean;
}

export interface Announcement {
  id: string;
  title: string;
  content: string;
  timeKind: AnnouncementTimeKind;
  eventAt: string;
  linkUrl: string | null;
  recruitmentId: string | null;
  /** 关联招募当前是否仍可访问 */
  recruitmentAvailable: boolean;
  author: PublicUser;
  createdAt: string;
  updatedAt: string;
  permissions: AnnouncementPermissions;
}

/** 普通用户投稿状态：待审核 / 已通过 / 已驳回 */
export type SubmissionStatus = 'pending' | 'approved' | 'rejected';

/** 本人投稿记录（GET /me/announcement-submissions） */
export interface AnnouncementSubmission {
  id: string;
  title: string;
  content: string;
  timeKind: AnnouncementTimeKind;
  eventAt: string;
  linkUrl: string | null;
  status: SubmissionStatus;
  submittedAt: string;
  reviewedAt: string | null;
  rejectReason: string | null;
  announcementId: string | null;
}

/** 管理员待审池条目（GET /admin/announcement-submissions） */
export interface PendingSubmission {
  id: string;
  title: string;
  content: string;
  timeKind: AnnouncementTimeKind;
  eventAt: string;
  linkUrl: string | null;
  submittedAt: string;
  submitter: PublicUser;
  claimedBy: PublicUser | null;
  claimedUntil: string | null;
  /** 超过 24 小时未处理 */
  overdue: boolean;
}

/** 领取成功后需原样带回的审核批次 */
export interface ClaimedSubmission extends AnnouncementSubmission {
  claimId: string;
  claimedUntil: string;
}

export type NotificationType =
  | 'application_submitted'
  | 'application_accepted'
  | 'application_rejected'
  | 'application_withdrawn'
  | 'application_updated'
  | 'anonymous_withdrawal'
  | 'recruitment_closed'
  | 'recruitment_updated'
  | 'recruitment_deleted'
  | 'announcement_admin_removed'
  | 'announcement_removed'
  | 'announcement_submission_approved'
  | 'announcement_submission_rejected'
  | 'admin_removed';

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  body: string; // 后端 content
  jobId?: string;
  applicationId?: string;
  announcementId?: string;
  /** 关联招聘/公告当前是否已删除（不等于申请状态） */
  targetIsDeleted: boolean;
  createdAt: string;
  read: boolean;
}

export interface Page<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

/** 后端分页接口每页最大条数（page_size 上限），前端请求不得超过该值 */
export const MAX_PAGE_SIZE = 50;

export interface JobQuery {
  type?: JobType | 'all';
  keyword?: string; // 后端 q
  tagId?: number; // 后端 tag（单个）
  status?: JobStatus;
  page: number;
  pageSize: number;
}
