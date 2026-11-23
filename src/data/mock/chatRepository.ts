import type { Conversation, Message, Page, PublicUser } from '@/domain/models';
import type { MessageRepository } from '@/data/ports';

/** 浏览器本地聊天演示仓储，数据保存在 localStorage。 */

const STORAGE_KEY = 'jiyu.demo.chat.v1';

interface ChatRow {
  id: string;
  peer: PublicUser;
  updatedAt: string;
}

interface PersistedChat {
  conversations: ChatRow[];
  messages: Message[];
  seq: number;
}

const DEMO_PEERS: PublicUser[] = [
  { id: 'demo-peer-1', name: '林同学', role: 'student' },
  { id: 'demo-peer-2', name: '周老师', role: 'teacher' },
];

function hoursAgo(n: number): string {
  return new Date(Date.now() - n * 3_600_000).toISOString();
}

function buildSeed(): PersistedChat {
  const messages: Message[] = [
    {
      id: 'demo-msg-1',
      conversationId: 'demo-conv-1',
      senderId: 'demo-peer-1',
      text: '同学你好，看到你在找竞赛组队的队友，还缺人吗？',
      createdAt: hoursAgo(26),
    },
    {
      id: 'demo-msg-2',
      conversationId: 'demo-conv-1',
      senderId: 'me',
      text: '还在招人，方便说下你熟悉的技术栈吗？',
      createdAt: hoursAgo(25),
    },
    {
      id: 'demo-msg-3',
      conversationId: 'demo-conv-1',
      senderId: 'demo-peer-1',
      text: '我主要做前端，React 和 TypeScript 都写过完整项目。',
      createdAt: hoursAgo(24),
    },
    {
      id: 'demo-msg-4',
      conversationId: 'demo-conv-2',
      senderId: 'demo-peer-2',
      text: '活动志愿者招募的简历已经收到，稍后统一答复。',
      createdAt: hoursAgo(6),
    },
  ];
  return {
    conversations: [
      { id: 'demo-conv-1', peer: DEMO_PEERS[0], updatedAt: hoursAgo(24) },
      { id: 'demo-conv-2', peer: DEMO_PEERS[1], updatedAt: hoursAgo(6) },
    ],
    messages,
    seq: 100,
  };
}

let cache: PersistedChat | null = null;

function load(): PersistedChat {
  if (cache) return cache;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      cache = JSON.parse(raw) as PersistedChat;
      return cache;
    }
  } catch {
    /* 存储损坏时回退到种子数据 */
  }
  cache = buildSeed();
  persist();
  return cache;
}

function persist(): void {
  try {
    const { conversations, messages, seq } = load();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ conversations, messages, seq }));
  } catch {
    /* 配额不足时仅保留内存态 */
  }
}

function paginate<T>(items: T[], page: number, pageSize: number): Page<T> {
  const start = (page - 1) * pageSize;
  return { items: items.slice(start, start + pageSize), page, pageSize, total: items.length };
}

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), 120));
}

/** 演示会话里「我」的发送方标识；真实后端会以当前用户 uid 代替 */
const SELF = 'me';

export function createChatRepository(getViewerId: () => string | null): MessageRepository {
  const ensureViewer = () => {
    if (!getViewerId()) throw new Error('请先登录后使用站内消息');
  };

  return {
    async listConversations(q) {
      await delay(null);
      if (!getViewerId()) return paginate([], q.page, q.pageSize);
      const { conversations, messages } = load();
      const rows: Conversation[] = conversations
        .map((c) => {
          const last = messages
            .filter((m) => m.conversationId === c.id)
            .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())[0];
          return {
            id: c.id,
            peer: c.peer,
            lastMessage: last ? { text: last.text, createdAt: last.createdAt, senderId: last.senderId } : null,
            updatedAt: c.updatedAt,
          };
        })
        .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
      return paginate(rows, q.page, q.pageSize);
    },

    async listMessages(conversationId, q) {
      await delay(null);
      ensureViewer();
      const { conversations, messages } = load();
      if (!conversations.some((c) => c.id === conversationId)) throw new Error('会话不存在');
      const rows = messages
        .filter((m) => m.conversationId === conversationId)
        .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
      return paginate(rows, q.page, q.pageSize);
    },

    async send(conversationId, text) {
      await delay(null);
      ensureViewer();
      const body = text.trim();
      if (!body) throw new Error('消息不能为空');
      const data = load();
      const conv = data.conversations.find((c) => c.id === conversationId);
      if (!conv) throw new Error('会话不存在');
      const message: Message = {
        id: `demo-msg-${++data.seq}`,
        conversationId,
        senderId: SELF,
        text: body,
        createdAt: new Date().toISOString(),
      };
      data.messages.push(message);
      conv.updatedAt = message.createdAt;
      persist();
      return structuredClone(message);
    },

    async openWith(userId) {
      await delay(null);
      ensureViewer();
      if (userId === SELF) throw new Error('不能与自己发起会话');
      const data = load();
      const existing = data.conversations.find((c) => c.peer.id === userId);
      if (existing) {
        return {
          id: existing.id,
          peer: existing.peer,
          lastMessage: null,
          updatedAt: existing.updatedAt,
        };
      }
      const peer = DEMO_PEERS.find((p) => p.id === userId) ?? {
        id: userId,
        name: '未知用户',
        role: 'student' as const,
      };
      const row: ChatRow = { id: `demo-conv-${++data.seq}`, peer, updatedAt: new Date().toISOString() };
      data.conversations.push(row);
      persist();
      return { id: row.id, peer: row.peer, lastMessage: null, updatedAt: row.updatedAt };
    },
  };
}
