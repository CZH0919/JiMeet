import type { Conversation, Job, JobQuery, Message, Page, UserRole } from '@/domain/models';
import type { CreateJobInput } from '@/domain/validation';
import { db, DomainError } from './db';
import type { ConversationRow } from './seed';

/**
 * 本地 mock 仓储：只负责后端暂未提供的「竞赛通知」与「站内聊天」。
 * 其余功能由 http/repository.ts 提供，两者在 data/index.ts 组合成混合仓储。
 */

function delay<T>(value: T, ms = 200): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));
}

function paginate<T>(items: T[], page: number, pageSize: number): { items: T[]; page: number; pageSize: number; total: number } {
  const start = (page - 1) * pageSize;
  return { items: items.slice(start, start + pageSize), page, pageSize, total: items.length };
}

function sortNotices(list: Job[]): Job[] {
  return [...list].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  );
}

function toConversation(row: ConversationRow, viewerId: string): Conversation {
  const peerId = row.participantIds.find((id) => id !== viewerId) ?? viewerId;
  const u = db.demoUsers.find((x) => x.id === peerId);
  const last = db.messages
    .filter((m) => m.conversationId === row.id)
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())[0];
  return {
    id: row.id,
    peer: { id: peerId, name: u?.name ?? '未知用户', role: u?.role ?? 'student' },
    lastMessage: last ? { text: last.text, createdAt: last.createdAt, senderId: last.senderId } : null,
    updatedAt: row.updatedAt,
  };
}

export interface LocalRepository {
  setCurrentUser(u: { id: string; name: string; role: UserRole } | null): void;
  jobs: {
    list(q: JobQuery): Promise<{ items: Job[]; page: number; pageSize: number; total: number }>;
    listMine(q: JobQuery): Promise<{ items: Job[]; page: number; pageSize: number; total: number }>;
    detail(id: string): Promise<Job>;
    create(input: CreateJobInput): Promise<Job>;
    update(id: string, input: CreateJobInput): Promise<Job>;
    close(id: string): Promise<Job>;
    remove(id: string): Promise<void>;
  };
  messages: {
    listConversations(q: { page: number; pageSize: number }): Promise<Page<Conversation>>;
    listMessages(conversationId: string, q: { page: number; pageSize: number }): Promise<Page<Message>>;
    send(conversationId: string, text: string): Promise<Message>;
    openWith(userId: string): Promise<Conversation>;
  };
}

export function createLocalRepository(): LocalRepository {
  return {
    setCurrentUser(u) {
      db.setCurrentUser(u);
    },

    jobs: {
      async list(q) {
        await delay(null, 120);
        let list = sortNotices(db.notices);
        if (q.keyword?.trim()) {
          const kw = q.keyword.trim().toLowerCase();
          list = list.filter(
            (j) => j.title.toLowerCase().includes(kw) || j.description.toLowerCase().includes(kw),
          );
        }
        return paginate(list, q.page, q.pageSize);
      },
      async listMine(q) {
        await delay(null, 120);
        const uid = db.getCurrentUser()?.id;
        const list = sortNotices(db.notices.filter((j) => uid && j.publisher.id === uid));
        return paginate(list, q.page, q.pageSize);
      },
      async detail(id) {
        await delay(null, 120);
        const n = db.notices.find((j) => j.id === id);
        if (!n) throw new DomainError('招聘不存在或已被删除');
        return n;
      },
      async create(input) {
        await delay(null, 150);
        const user = db.getCurrentUser();
        if (!user) throw new DomainError('请先登录');
        const now = new Date().toISOString();
        const notice: Job = {
          id: db.nextId('notice'),
          type: 'competition_notice',
          title: input.title.trim(),
          description: input.description.trim(),
          tags: input.tags,
          minHeadcount: null,
          maxHeadcount: 0,
          acceptedCount: 0,
          deadline: input.deadline,
          status: 'open',
          isDeleted: false,
          publisher: { id: user.id, name: user.name, role: user.role },
          createdAt: now,
          updatedAt: now,
          applicationCount: 0,
        };
        db.setNotices([notice, ...db.notices]);
        return notice;
      },
      async update(id, input) {
        await delay(null, 150);
        const user = db.getCurrentUser();
        const n = db.notices.find((j) => j.id === id);
        if (!n) throw new DomainError('招聘不存在或已被删除');
        if (!user || n.publisher.id !== user.id) throw new DomainError('仅可编辑本人发布的竞赛通知');
        if (n.status !== 'open') throw new DomainError('仅进行中状态可修改');
        n.title = input.title.trim();
        n.description = input.description.trim();
        n.tags = input.tags;
        n.deadline = input.deadline;
        n.updatedAt = new Date().toISOString();
        db.save();
        return n;
      },
      async close() {
        throw new DomainError('竞赛通知不支持手动关闭');
      },
      async remove(id) {
        await delay(null, 120);
        const user = db.getCurrentUser();
        const n = db.notices.find((j) => j.id === id);
        if (!n) throw new DomainError('招聘不存在或已被删除');
        if (!user || n.publisher.id !== user.id) throw new DomainError('仅可删除本人发布的竞赛通知');
        db.setNotices(db.notices.filter((j) => j.id !== id));
      },
    },

    messages: {
      async listConversations(q) {
        await delay(null, 120);
        const user = db.getCurrentUser();
        if (!user) return paginate([], q.page, q.pageSize);
        const list = db.conversations
          .filter((c) => c.participantIds.includes(user.id))
          .map((c) => toConversation(c, user.id))
          .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
        return paginate(list, q.page, q.pageSize);
      },
      async listMessages(conversationId, q) {
        await delay(null, 120);
        const user = db.getCurrentUser();
        if (!user) throw new DomainError('请先登录');
        const conv = db.conversations.find((c) => c.id === conversationId);
        if (!conv || !conv.participantIds.includes(user.id)) throw new DomainError('会话不存在');
        const list = db.messages
          .filter((m) => m.conversationId === conversationId)
          .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
        return paginate(list, q.page, q.pageSize);
      },
      async send(conversationId, text) {
        await delay(null, 120);
        const user = db.getCurrentUser();
        if (!user) throw new DomainError('请先登录');
        const conv = db.conversations.find((c) => c.id === conversationId);
        if (!conv || !conv.participantIds.includes(user.id)) throw new DomainError('会话不存在');
        const body = text.trim();
        if (!body) throw new DomainError('消息不能为空');
        const message: Message = {
          id: db.nextId('msg'),
          conversationId,
          senderId: user.id,
          text: body,
          createdAt: new Date().toISOString(),
        };
        db.setMessages([...db.messages, message]);
        conv.updatedAt = message.createdAt;
        db.save();
        return message;
      },
      async openWith(userId) {
        await delay(null, 120);
        const user = db.getCurrentUser();
        if (!user) throw new DomainError('请先登录');
        if (userId === user.id) throw new DomainError('不能与自己发起会话');
        const existing = db.conversations.find(
          (c) => c.participantIds.includes(user.id) && c.participantIds.includes(userId),
        );
        if (existing) return toConversation(existing, user.id);
        const row: ConversationRow = {
          id: db.nextId('conv'),
          participantIds: [user.id, userId],
          updatedAt: new Date().toISOString(),
        };
        db.conversations.push(row);
        db.save();
        return toConversation(row, user.id);
      },
    },
  };
}
