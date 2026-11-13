export type UserRole = 'student' | 'teacher';

/** 本人资料（GET /me）映射后的领域模型；id 即后端 32 位十六进制 uid */
export interface User {
  id: string; // uid
  name: string; // 展示名（后端 nickname）
  role: UserRole;
  isAdmin: boolean;
  email?: string;
  privacyConsented: boolean;
}

/**
 * 招聘类型。competition / activity / internship 来自后端；
 * competition_notice 为前端本地特性（后端暂未提供），仅走 mock。
 */
export type JobType = 'competition' | 'activity' | 'internship' | 'competition_notice';

/** 招募中 / 已满员 / 已关闭 */
export type JobStatus = 'open' | 'full' | 'closed';

export interface Tag {
  id: number;
  name: string;
}

export interface Job {
  id: string; // 后端正整数 id 转字符串；mock 通知用 'job-N'
  type: JobType;
  title: string;
  description: string;
  tags: Tag[];
  minHeadcount: number | null;
  maxHeadcount: number;
  acceptedCount: number;
  deadline: string; // ISO8601（带时区）
  status: JobStatus;
  isDeleted: boolean;
  publisher: Pick<User, 'id' | 'name' | 'role'>;
  createdAt: string;
  updatedAt: string;
  /** 仅详情接口返回（列表 summary 不含）；有值时用于卡片「已申请」提示 */
  myApplicationStatus?: ApplicationStatus | null;
  /** 详情接口对发布者返回的五态计数之和 */
  applicationCount: number;
  /** 详情接口 permissions 映射，用于投递按钮展示；写操作仍由后端重新校验 */
  permissions?: {
    canApply: boolean;
    canEdit: boolean;
    canClose: boolean;
    canDelete: boolean;
    canViewApplications: boolean;
    /** 后端返回的展示文案（可空），仅用于展示，不作为判断依据 */
    applyBlockedReason: string | null;
    /** 后端返回的原始业务错误码（可空），用于区分软阻塞（如隐私告知未确认） */
    applyBlockedCode: string | null;
  };
}

/** 处理中 / 已接受 / 已拒绝 / 已撤回 / 已失效；除处理中外均为终态 */
export type ApplicationStatus = 'processing' | 'accepted' | 'rejected' | 'withdrawn' | 'invalid';

export interface ResumeFile {
  fileName: string;
  size: number; // 字节
  type: string; // pdf | doc | docx
}

export interface Application {
  id: string;
  jobId: string;
  jobTitle: string;
  jobType: JobType;
  applicant: Pick<User, 'id' | 'name' | 'role'>;
  /** null 表示简历已不可见（撤回/失效） */
  resume: ResumeFile | null;
  note?: string;
  status: ApplicationStatus;
  createdAt: string;
  updatedAt: string;
  /** 发布者私有标记：hold 表示暂留（仍为 processing） */
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
  peer: Pick<User, 'id' | 'name' | 'role'>;
  lastMessage: Pick<Message, 'text' | 'createdAt' | 'senderId'> | null;
  updatedAt: string;
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
  | 'admin_removed';

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  body: string; // 后端 content
  jobId?: string; // recruitment_id
  applicationId?: string;
  createdAt: string;
  read: boolean;
}

export interface Page<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

/** 后端分页接口每页最大条数（page_size 上限），前端请求 page_size 不得超过该值。 */
export const MAX_PAGE_SIZE = 50;

export interface JobQuery {
  type?: JobType | 'all';
  keyword?: string; // 后端 q
  tagId?: number; // 后端 tag（单个）
  status?: JobStatus;
  page: number;
  pageSize: number;
}
