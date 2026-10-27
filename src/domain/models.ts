export type UserRole = 'student' | 'teacher';

export interface User {
  id: string; // 学号 / 工号
  name: string;
  email: string;
  role: UserRole;
  isAdmin: boolean;
  college?: string;
  major?: string;
  avatarUrl?: string;
}

export type JobType = 'competition' | 'campus_activity';
/** 招募中 / 已满员 / 已关闭 */
export type JobStatus = 'open' | 'full' | 'closed';

export interface Job {
  id: string;
  type: JobType;
  title: string;
  description: string;
  requirement: string;
  field: string; // 相关领域：计算机 / 设创 / 商学 / 工程 ...
  recruitCount: number;
  acceptedCount: number;
  deadline: string; // ISO8601
  status: JobStatus;
  publisher: Pick<User, 'id' | 'name' | 'role'>;
  createdAt: string;
  updatedAt: string;
  myApplicationStatus?: ApplicationStatus | null;
  applicationCount: number;
}

/** 处理中 / 已接受 / 已拒绝 / 已撤回；后三者为终态 */
export type ApplicationStatus = 'pending' | 'accepted' | 'rejected' | 'withdrawn';

export interface ResumeFile {
  id: string;
  fileName: string;
  size: number;
  mimeType: string;
  uploadedAt: string;
  downloadUrl?: string;
}

export interface Application {
  id: string;
  jobId: string;
  jobTitle: string;
  jobType: JobType;
  applicant: Pick<User, 'id' | 'name' | 'role'>;
  resume: ResumeFile;
  note?: string;
  status: ApplicationStatus;
  createdAt: string;
  updatedAt: string;
  resumeHidden: boolean;
}

/** 站内纯文本消息（设计稿第 13 页：任意两用户可对话） */
export interface Message {
  id: string;
  conversationId: string;
  senderId: string;
  text: string;
  createdAt: string;
}

/** 会话（当前用户视角：peer 是对方，lastMessage 用于列表预览） */
export interface Conversation {
  id: string;
  peer: Pick<User, 'id' | 'name' | 'role'>;
  lastMessage: Pick<Message, 'text' | 'createdAt' | 'senderId'> | null;
  updatedAt: string;
}

export type NotificationType =
  | 'application_accepted'
  | 'application_rejected'
  | 'application_withdrawn'
  | 'job_removed_by_admin'
  | 'job_modified'
  | 'job_closed';

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  jobId?: string;
  jobTitle?: string;
  recipientId: string; // 接收者用户 id
  createdAt: string;
  read: boolean;
}

export interface AuditLog {
  id: string;
  operatorId: string;
  operatorName: string;
  operatorRole: UserRole;
  targetType: 'job';
  targetId: string;
  targetTitle: string;
  action: 'delete_job';
  reason: string;
  createdAt: string;
}

export interface Page<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export interface JobQuery {
  type?: JobType | 'all';
  keyword?: string;
  field?: string;
  minRecruit?: number;
  deadlineWithin?: number; // 截止时间在 N 天内
  sort?: 'latest' | 'earliest';
  page: number;
  pageSize: number;
}
