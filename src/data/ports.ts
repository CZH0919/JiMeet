import type {
  Application,
  AuditLog,
  Conversation,
  Job,
  JobQuery,
  Message,
  Notification,
  Page,
  ResumeFile,
  User,
} from '@/domain/models';
import type { CreateJobInput } from '@/domain/validation';

/** Repository 端口（VGA 插座）。UI 层只依赖这些接口，通过 DI 拿到实例。 */

export class AuthUnavailableError extends Error {
  constructor() {
    super('统一身份认证服务暂时不可用，请稍后重试');
  }
}

export interface AuthRepository {
  login(): Promise<User>;
  loginWithEmail(email: string): Promise<User>;
  logout(): Promise<void>;
  getCurrentUser(): Promise<User | null>;
  /** 演示用：切换为指定 mock 用户 */
  loginAs(userId: string): Promise<User>;
}

export interface JobRepository {
  list(q: JobQuery): Promise<Page<Job>>;
  detail(id: string): Promise<Job>;
  create(input: CreateJobInput): Promise<Job>;
  update(id: string, input: CreateJobInput): Promise<Job>;
  close(id: string): Promise<Job>;
  remove(id: string): Promise<{ affectedPending: number; affectedAccepted: number }>;
  listMine(q: JobQuery): Promise<Page<Job>>;
}

export interface ApplicationRepository {
  submit(input: { jobId: string; resume: ResumeFile; note?: string }): Promise<Application>;
  withdraw(applicationId: string): Promise<Application>;
  listMine(q: { page: number; pageSize: number }): Promise<Page<Application>>;
  listForJob(jobId: string, q: { page: number; pageSize: number }): Promise<Page<Application>>;
  mark(applicationId: string, action: 'accept' | 'hold' | 'reject'): Promise<Application>;
}

export interface NotificationRepository {
  list(q: { page: number; pageSize: number }): Promise<Page<Notification>>;
  markRead(id: string): Promise<void>;
  markAllRead(): Promise<void>;
  unreadCount(): Promise<number>;
}

export interface AdminRepository {
  listAllJobs(q: JobQuery): Promise<Page<Job>>;
  removeJobWithReason(jobId: string, reason: string): Promise<void>;
  listAuditLogs(q: { page: number; pageSize: number }): Promise<Page<AuditLog>>;
}

export interface FileRepository {
  uploadResume(file: File, onProgress?: (p: number) => void): Promise<ResumeFile>;
}

export interface MessageRepository {
  /** 会话列表（含对方信息与最后一条消息） */
  listConversations(q: { page: number; pageSize: number }): Promise<Page<Conversation>>;
  /** 某会话的消息，按时间升序 */
  listMessages(
    conversationId: string,
    q: { page: number; pageSize: number },
  ): Promise<Page<Message>>;
  /** 发送纯文本消息，返回落库后的消息 */
  send(conversationId: string, text: string): Promise<Message>;
  /** 与指定用户发起 / 复用会话（设计稿：任意两用户可对话） */
  openWith(userId: string): Promise<Conversation>;
}

export interface Repositories {
  auth: AuthRepository;
  jobs: JobRepository;
  applications: ApplicationRepository;
  notifications: NotificationRepository;
  admin: AdminRepository;
  files: FileRepository;
  messages: MessageRepository;
}
