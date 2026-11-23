import type { Repositories } from './ports';
import { createHttpRepository } from './http/repository';
import { createChatRepository } from './mock/chatRepository';
import { useSession } from '@/stores/session';

/**
 * 依赖注入的唯一开关。
 *
 * - 账号、招聘、公告、申请、通知、治理：后端 HTTP（data/http）
 * - 站内聊天：使用浏览器本地演示仓储（data/mock）
 *
 * UI 层统一从 `repo` 取实例，不感知底层来源。
 */
let instance: Repositories | null = null;

export function getRepositories(): Repositories {
  if (!instance) {
    const http = createHttpRepository();
    instance = {
      ...http,
      messages: createChatRepository(() => useSession.getState().user?.id ?? null),
    };
  }
  return instance;
}

/** 全局单例 */
export const repo: Repositories = getRepositories();
