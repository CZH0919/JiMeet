import type {
  Announcement,
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
import type { AnnouncementInput, CreateJobInput, LoginInput, RegisterInput } from '@/domain/validation';

/**
 * Repository 端口（VGA 插座）。UI 层只依赖这些接口，通过 DI 拿到实例。
 * 端口命名按业务语义，不出现后端路径；实现见 data/http 与 data/mock。
 */

export interface AuthRepository {
  register(input: RegisterInput): Promise<User>;
  login(input: LoginInput): Promise<User>;
  /** 开发登录（后端 dev-login，输入编号 real_id）；仅用于隔离调试，不替代正式注册登录 */
  devLogin(realId: string): Promise<User>;
  logout(): Promise<void>;
  getCurrentUser(): Promise<User | null>;
  /** 修改昵称（PATCH /me）；邮箱与姓名不可在此修改 */
  updateProfile(input: { nickname: string }): Promise<User>;
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
  /** 本人删除（发布者入口）；原因可选 */
  remove(id: string, reason?: string): Promise<void>;
  listMine(q: JobQuery): Promise<Page<Job>>;
}

export interface AnnouncementRepository {
  list(q: { page: number; pageSize: number }): Promise<Page<Announcement>>;
  detail(id: string): Promise<Announcement>;
  create(input: AnnouncementInput): Promise<Announcement>;
  update(id: string, input: AnnouncementInput): Promise<Announcement>;
  /** 本人删除：软删除，不需要原因，不产生通知 */
  removeOwn(id: string): Promise<void>;
  /** 治理删除：原因必填，通知作者并记入审计 */
  governRemove(id: string, reason: string): Promise<void>;
}

export interface ApplicationRepository {
  /** 提交申请：简历文件随 multipart 一起上传 */
  submit(input: { jobId: string; resumeFile: File; note?: string }): Promise<Application>;
  /** 申请详情（含 note / resume 元数据，列表接口不返回） */
  detail(applicationId: string): Promise<Application>;
  /** 修改本人处理中的申请：新版简历覆盖旧版（不传 resumeFile 则沿用旧版） */
  update(applicationId: string, input: { resumeFile?: File; note?: string }): Promise<Application>;
  withdraw(applicationId: string): Promise<Application>;
  listMine(q: { page: number; pageSize: number; status?: string }): Promise<Page<Application>>;
  listForJob(
    jobId: string,
    q: { page: number; pageSize: number; status?: string },
  ): Promise<Page<Application>>;
  mark(applicationId: string, action: 'accept' | 'hold' | 'reject' | 'unhold'): Promise<Application>;
  /** 发布者查看简历后确认「已修改」已阅 */
  clearModified(applicationId: string, seenUpdatedAt: string): Promise<void>;
  /** 下载简历文件（浏览器触发），失败抛错 */
  downloadResume(applicationId: string): Promise<void>;
  /** 读取简历内容用于在线预览（同一鉴权接口，不产生公开链接） */
  resumeBlob(applicationId: string): Promise<Blob>;
}

export interface NotificationRepository {
  list(q: { page: number; pageSize: number; isRead?: boolean }): Promise<Page<Notification>>;
  markRead(id: string): Promise<void>;
  /** 返回本次实际更新条数 */
  markAllRead(): Promise<number>;
  unreadCount(): Promise<number>;
}

export interface AdminRepository {
  listAllJobs(q: JobQuery): Promise<Page<Job>>;
  /** 治理删除招聘：原因必填 */
  governRemoveJob(jobId: string, reason: string): Promise<void>;
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
  announcements: AnnouncementRepository;
  applications: ApplicationRepository;
  notifications: NotificationRepository;
  admin: AdminRepository;
  messages: MessageRepository;
}
