/**
 * 前端页面使用的领域模型。
 * UI 层只认这里定义的字段，后端 snake_case、枚举、可空语义都在 data/http/mappers.ts 收口。
 */

export type UserRole = 'student' | 'teacher';

/** 公共用户：后端只暴露 uid / nickname / role，不含姓名、邮箱 */
export interface PublicUser {
  id: string; // 32 位十六进制 uid
  name: string; // 展示名（nickname）
  role: UserRole;
}

/** 本人资料（GET /me） */
export interface User {
  id: string;
  name: string;
  role: UserRole;
  isAdmin: boolean;
  email?: string;
  privacyConsented: boolean;
  /** 兼容字段：不代表可用邮件功能，前端不作为开关展示 */
  emailNotifyEnabled: boolean;
}

/** 招聘类型（后端 competition / activity / internship） */
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

export interface Message {
  id: string;
  conversationId: string;
  senderId: string;
  text: string;
  createdAt: string;
}

export interface Conversation {
  id: string;
  peer: PublicUser;
  lastMessage: Pick<Message, 'text' | 'createdAt' | 'senderId'> | null;
  updatedAt: string;
}

/** 公告时间类型：报名截止时间 / 活动时间 */
export type AnnouncementTimeKind = 'deadline' | 'event';

export interface AnnouncementPermissions {
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

export type NotificationType =
  | 'application_submitted'
  | 'application_accepted'
  | 'application_rejected'
  | 'application_withdrawn'
  | 'application_updated'
  | 'recruitment_closed'
  | 'recruitment_updated'
  | 'recruitment_deleted'
  | 'announcement_admin_removed'
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
