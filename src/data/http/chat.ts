import type { Conversation, Message, Page, PeerProfile } from '@/domain/models';
import type { ContactSource, Repositories } from '@/data/ports';
import { http } from './client';
import {
  mapConversation,
  mapConversationPage,
  mapMessage,
  mapMessagePage,
  mapPeerProfile,
} from './mappers';

/**
 * 对方主页与站内聊天仓储。
 * 契约见 backend/design_file/api.md 第 10 章：首次联系须带来源，已有会话可复用；
 * 页面按时间正序渲染，回翻用当前最早一条消息的 before_id，回执只提交实际展示的对方消息。
 */

/** 路径与查询参数用字符串编号，JSON 请求体按契约统一传整数 */
function idOf(value: string): number {
  return Number(value);
}

function toSourceBody(source?: ContactSource): Record<string, unknown> {
  if (!source) return {};
  const body: Record<string, unknown> = {};
  if (source.recruitmentId) body.recruitment_id = idOf(source.recruitmentId);
  if (source.applicationId) body.application_id = idOf(source.applicationId);
  return body;
}

export function createHttpUserRepository(): Repositories['users'] {
  return {
    async getPeer(uid: string, source?: ContactSource): Promise<PeerProfile> {
      const query: Record<string, string | number | undefined> = {};
      if (source?.recruitmentId) query.recruitment_id = idOf(source.recruitmentId);
      if (source?.applicationId) query.application_id = idOf(source.applicationId);
      const data = await http.get<Record<string, unknown>>(`/users/${encodeURIComponent(uid)}`, query);
      return mapPeerProfile(data);
    },
  };
}

export function createHttpMessageRepository(): Repositories['messages'] {
  return {
    async listConversations(q: { page: number; pageSize: number }): Promise<Page<Conversation>> {
      const data = await http.get<Record<string, unknown>>('/chat/conversations', {
        page: q.page,
        page_size: q.pageSize,
      });
      return mapConversationPage(data);
    },

    async listMessages(
      conversationId: string,
      q: { page: number; pageSize: number; beforeId?: string },
    ): Promise<Page<Message>> {
      const data = await http.get<Record<string, unknown>>(
        `/chat/conversations/${conversationId}/messages`,
        {
          page: q.page,
          page_size: q.pageSize,
          before_id: q.beforeId ? idOf(q.beforeId) : undefined,
        },
      );
      return mapMessagePage(data);
    },

    async send(conversationId: string, text: string): Promise<Message> {
      const data = await http.post<Record<string, unknown>>(
        `/chat/conversations/${conversationId}/messages`,
        { content: text },
      );
      return mapMessage(data);
    },

    async openWith(peerUid: string, source?: ContactSource): Promise<Conversation> {
      const data = await http.post<Record<string, unknown>>('/chat/conversations', {
        peer_uid: peerUid,
        ...toSourceBody(source),
      });
      return mapConversation(data);
    },

    async markRead(conversationId: string, messageIds: string[]): Promise<number> {
      if (messageIds.length === 0) return 0;
      const data = await http.post<{ updated_count: number }>(
        `/chat/conversations/${conversationId}/read`,
        { message_ids: messageIds.map(idOf) },
      );
      return Number(data?.updated_count ?? 0);
    },

    async unreadCount(): Promise<number> {
      const data = await http.get<{ unread_count: number }>('/chat/conversations/unread-count');
      return Number(data.unread_count ?? 0);
    },
  };
}
