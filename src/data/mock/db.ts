import type { Job, Message, UserRole } from '@/domain/models';
import { buildSeed, type ConversationRow, type DemoUser } from './seed';

/** 本地内存 + localStorage 持久化（仅竞赛通知 + 聊天，刷新不丢）。 */

const STORAGE_KEY = 'jiyu.mock.local.v1';

interface PersistedShape {
  notices: Job[];
  demoUsers: DemoUser[];
  conversations: ConversationRow[];
  messages: Message[];
  seq: number;
}

export class DomainError extends Error {}

let cache: PersistedShape | null = null;

function load(): PersistedShape {
  if (cache) return cache;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      cache = JSON.parse(raw) as PersistedShape;
      return cache;
    }
  } catch {
    /* ignore corrupted storage */
  }
  cache = { ...buildSeed(), seq: 100 };
  persist();
  return cache;
}

function persist() {
  try {
    const { notices, demoUsers, conversations, messages, seq } = load();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ notices, demoUsers, conversations, messages, seq }));
  } catch {
    /* quota exceeded — keep in-memory */
  }
}

/** 当前登录用户（由 hybrid 层在登录/登出时同步，不持久化） */
let currentUser: { id: string; name: string; role: UserRole } | null = null;

export const db = {
  get notices(): Job[] {
    return load().notices;
  },
  setNotices(list: Job[]) {
    load().notices = list;
    persist();
  },
  get demoUsers(): DemoUser[] {
    return load().demoUsers;
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
  nextId(prefix: string): string {
    const d = load();
    d.seq += 1;
    persist();
    return `${prefix}-${d.seq}`;
  },
  save() {
    persist();
  },
  getCurrentUser() {
    return currentUser;
  },
  setCurrentUser(u: { id: string; name: string; role: UserRole } | null) {
    currentUser = u;
  },
};
