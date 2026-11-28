import type { Repositories } from './ports';
import { createHttpRepository } from './http/repository';
import { createHttpMessageRepository, createHttpUserRepository } from './http/chat';

/**
 * 依赖注入的唯一入口。
 *
 * 账号、招聘、公告及投稿、申请、通知、治理、对方主页与聊天全部走后端 HTTP（data/http）。
 * UI 层统一从 `repo` 取实例，不感知底层来源，也不直接拼接接口路径。
 */
let instance: Repositories | null = null;

export function getRepositories(): Repositories {
  if (!instance) {
    instance = {
      ...createHttpRepository(),
      users: createHttpUserRepository(),
      messages: createHttpMessageRepository(),
    };
  }
  return instance;
}

/** 全局单例 */
export const repo: Repositories = getRepositories();
