import type {
  Application,
  Conversation,
  Job,
  JobQuery,
  Message,
  Notification,
  Page,
  Tag,
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
  /** 开发登录（后端 dev-login，输入编号 real_id） */
  devLogin(realId: string): Promise<User>;
  logout(): Promise<void>;
  getCurrentUser(): Promise<User | null>;
  /** 仅在用户主动确认个人信息处理告知后调用 */
  confirmPrivacyConsent(): Promise<User>;
}

export interface JobRepository {
  listTags(): Promise<Tag[]>;
  list(q: JobQuery): Promise<Page<Job>>;
  detail(id: string): Promise<Job>;
  create(input: CreateJobInput): Promise<Job>;
  update(id: string, input: CreateJobInput): Promise<Job>;
  close(id: string): Promise<Job>;
  /** 发布者删除可省略原因；管理员删除必须给 reason */
  remove(id: string, reason?: string): Promise<void>;
  listMine(q: JobQuery): Promise<Page<Job>>;
}

export interface ApplicationRepository {
  /** 提交申请：简历文件随 multipart 一起上传 */
  submit(input: { jobId: string; resumeFile: File; note?: string }): Promise<Application>;
  /** 申请详情（含 note / resume 元数据，列表接口不返回） */
  detail(applicationId: string): Promise<Application>;
  /** 修改本人处理中的申请：新版简历覆盖旧版（不传 resumeFile 则沿用旧版） */
  update(applicationId: string, input: { resumeFile?: File; note?: string }): Promise<Application>;
  withdraw(applicationId: string): Promise<Application>;
  listMine(q: { page: number; pageSize: number }): Promise<Page<Application>>;
  listForJob(jobId: string, q: { page: number; pageSize: number }): Promise<Page<Application>>;
  mark(applicationId: string, action: 'accept' | 'hold' | 'reject'): Promise<Application>;
  /** 发布者查看简历后确认「已修改」已阅 */
  clearModified(applicationId: string, seenUpdatedAt: string): Promise<void>;
  /** 下载简历文件（浏览器触发），失败抛错 */
  downloadResume(applicationId: string): Promise<void>;
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
}

/** 聊天（后端暂未提供，保留本地 mock） */
export interface MessageRepository {
  listConversations(q: { page: number; pageSize: number }): Promise<Page<Conversation>>;
  listMessages(
    conversationId: string,
    q: { page: number; pageSize: number },
  ): Promise<Page<Message>>;
  send(conversationId: string, text: string): Promise<Message>;
  openWith(userId: string): Promise<Conversation>;
}

export interface Repositories {
  auth: AuthRepository;
  jobs: JobRepository;
  applications: ApplicationRepository;
  notifications: NotificationRepository;
  admin: AdminRepository;
  messages: MessageRepository;
}
