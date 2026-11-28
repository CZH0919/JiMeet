import type {
  Announcement,
  AnnouncementSubmission,
  Application,
  ClaimedSubmission,
  Conversation,
  Job,
  JobQuery,
  Message,
  Notification,
  Page,
  PeerProfile,
  PendingSubmission,
  Tag,
  User,
} from '@/domain/models';
import type {
  AnnouncementInput,
  CreateJobInput,
  LoginInput,
  RegisterInput,
  SubmissionInput,
} from '@/domain/validation';

/**
 * Repository 端口（VGA 插座）。UI 层只依赖这些接口，通过 DI 拿到实例。
 * 端口命名按业务语义，不出现后端路径；实现见 data/http。
 */

/** 发码受理结果：验证码有效期与重发冷却，单位秒 */
export interface CodeSendResult {
  expiresIn: number;
  resendAfter: number;
}

/** 验码结果：`accountExists=true` 时不再签发建号资格，应引导登录 */
export interface CodeVerifyResult {
  accountExists: boolean;
  expiresIn: number;
}

export interface AuthRepository {
  /** 注册发码（同一会话内验码）；已注册邮箱得到相同受理响应 */
  sendRegisterCode(email: string): Promise<CodeSendResult>;
  /** 注册验码；只有成功后才由服务端提示邮箱是否已注册 */
  verifyRegisterCode(email: string, code: string): Promise<CodeVerifyResult>;
  register(input: RegisterInput): Promise<User>;
  /** 登录发码：与注册验证码共享 60 秒重发间隔与额度 */
  sendLoginCode(email: string): Promise<CodeSendResult>;
  login(input: LoginInput): Promise<User>;
  logout(): Promise<void>;
  getCurrentUser(): Promise<User | null>;
  /** 修改昵称（PATCH /me）；邮箱与姓名不可在此修改 */
  updateProfile(input: { nickname: string }): Promise<User>;
  /** 仅在用户主动确认个人信息处理告知后调用 */
  confirmPrivacyConsent(): Promise<User>;
  /** 注销本人账号：成功后原会话与各设备会话立即失效 */
  cancelAccount(): Promise<void>;
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
  /** 管理员直接发布（跳过审核） */
  create(input: AnnouncementInput): Promise<Announcement>;
  /** 本人删除：软删除，不需要原因，通知发布人与投稿人 */
  removeOwn(id: string): Promise<void>;
  /** 治理删除：原因必填，通知作者并记入审计 */
  governRemove(id: string, reason: string): Promise<void>;

  /** 普通用户投稿：提交后不能改稿、撤回 */
  submit(input: SubmissionInput): Promise<AnnouncementSubmission>;
  /** 本人投稿记录（含驳回理由与生成公告引用） */
  listMineSubmissions(q: { page: number; pageSize: number }): Promise<Page<AnnouncementSubmission>>;
  /** 管理员共享待审池：仅待审稿，逾期优先 */
  listPendingSubmissions(q: { page: number; pageSize: number }): Promise<Page<PendingSubmission>>;
  /** 待审总数，用于工作台红点 */
  pendingSubmissionCount(): Promise<number>;
  /** 领取 15 分钟审核权，返回本次批次 claim_id */
  claimSubmission(id: string): Promise<ClaimedSubmission>;
  /** 交回本次领取 */
  releaseSubmission(id: string, claimId: string): Promise<AnnouncementSubmission>;
  /** 按投稿原文发布，公开署名为审核管理员 */
  approveSubmission(id: string, claimId: string): Promise<AnnouncementSubmission>;
  /** 驳回并附理由 */
  rejectSubmission(id: string, claimId: string, reason: string): Promise<void>;
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

/** 首次联系来源：从招聘详情联系发布者，或从申请列表联系申请人 */
export interface ContactSource {
  recruitmentId?: string;
  applicationId?: string;
}

export interface UserRepository {
  /** 对方主页：只含公开资料与聊天入口；首次联系须提供来源 */
  getPeer(uid: string, source?: ContactSource): Promise<PeerProfile>;
}

/** 聊天页面读取会话和收发消息的仓储接口。 */
export interface MessageRepository {
  listConversations(q: { page: number; pageSize: number }): Promise<Page<Conversation>>;
  listMessages(
    conversationId: string,
    q: { page: number; pageSize: number; beforeId?: string },
  ): Promise<Page<Message>>;
  send(conversationId: string, text: string): Promise<Message>;
  /** 创建或复用双方唯一会话 */
  openWith(peerUid: string, source?: ContactSource): Promise<Conversation>;
  /** 对实际展示的对方消息提交已读回执，返回本次更新条数 */
  markRead(conversationId: string, messageIds: string[]): Promise<number>;
  /** 跨会话未读消息总数（与站内通知分别计数） */
  unreadCount(): Promise<number>;
}

export interface Repositories {
  auth: AuthRepository;
  jobs: JobRepository;
  announcements: AnnouncementRepository;
  applications: ApplicationRepository;
  notifications: NotificationRepository;
  admin: AdminRepository;
  users: UserRepository;
  messages: MessageRepository;
}
