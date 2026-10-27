import type { Application, AuditLog, Job, Message, Notification, User } from '@/domain/models';
import { buildSeed, type ConversationRow } from './seed';

/** 内存数据库 + localStorage 持久化（刷新不丢，便于演示）。 */

// v2：新增 conversations / messages，旧缓存结构不兼容，直接换 key 丢弃
const STORAGE_KEY = 'jiyu.mock.db.v2';

interface DBShape {
  users: User[];
  jobs: Job[];
  applications: Application[];
  notifications: Notification[];
  auditLogs: AuditLog[];
  conversations: ConversationRow[];
  messages: Message[];
  currentUserId: string | null;
  seq: number;
}

export class DomainError extends Error {}

let cache: DBShape | null = null;

function load(): DBShape {
  if (cache) return cache;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      cache = JSON.parse(raw) as DBShape;
      return cache!;
    }
  } catch {
    /* ignore corrupted storage */
  }
  const seed = buildSeed();
  // 依据申请推导计数
  for (const job of seed.jobs) {
    job.acceptedCount = seed.applications.filter((a) => a.jobId === job.id && a.status === 'accepted').length;
    job.applicationCount = seed.applications.filter((a) => a.jobId === job.id).length;
  }
  // 满员招聘状态与申请一致
  for (const job of seed.jobs) {
    if (job.acceptedCount >= job.recruitCount) job.status = 'full';
  }
  cache = {
    ...seed,
    currentUserId: null,
    seq: 1000,
  };
  persist();
  return cache;
}

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cache));
  } catch {
    /* quota exceeded — keep in-memory */
  }
}

export function resetDb() {
  cache = null;
  localStorage.removeItem(STORAGE_KEY);
  load();
}

export const db = {
  get users(): User[] {
    return load().users;
  },
  get jobs(): Job[] {
    return load().jobs;
  },
  get applications(): Application[] {
    return load().applications;
  },
  get notifications(): Notification[] {
    return load().notifications;
  },
  get auditLogs(): AuditLog[] {
    return load().auditLogs;
  },
  get conversations(): ConversationRow[] {
    return load().conversations;
  },
  get messages(): Message[] {
    return load().messages;
  },
  setMessages(list: Message[]) {
    load().messages = list;
    persist();
  },
  get currentUserId(): string | null {
    return load().currentUserId;
  },
  setCurrentUser(id: string | null) {
    load().currentUserId = id;
    persist();
  },
  setJobs(list: Job[]) {
    load().jobs = list;
    persist();
  },
  setApplications(list: Application[]) {
    load().applications = list;
    persist();
  },
  nextId(prefix: string): string {
    const d = load();
    d.seq += 1;
    persist();
    return `${prefix}-${d.seq}`;
  },
  save() {
    persist();
  },
  pushNotification(n: Omit<Notification, 'id' | 'createdAt' | 'read'>) {
    const d = load();
    d.seq += 1;
    d.notifications.unshift({
      ...n,
      id: `n-${d.seq}`,
      createdAt: new Date().toISOString(),
      read: false,
    });
    persist();
  },
};

/** 申请提交的前置校验（复刻真实业务规则，供 Mock/Http 层共用） */
export function assertCanSubmit(job: Job, userId: string, existing: Application[]) {
  if (job.status !== 'open') throw new DomainError('仅进行中状态可投递申请');
  if (new Date(job.deadline).getTime() < Date.now()) throw new DomainError('该招聘已过截止时间');
  if (job.publisher.id === userId) throw new DomainError('不可申请本人发布的招聘');
  if (existing.some((a) => a.jobId === job.id && a.applicant.id === userId && a.status !== 'withdrawn'))
    throw new DomainError('你已申请过该招聘，不可重复申请');
}
