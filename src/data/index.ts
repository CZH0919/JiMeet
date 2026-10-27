import type { Repositories } from './ports';
import { createMockRepository, installMockHelpers } from './mock/repository';

/**
 * 依赖注入（换接口的唯一开关）。
 * 后端就绪后：改 VITE_USE_MOCK=false 即切换为 HttpRepository，代码零改动。
 */
let instance: Repositories | null = null;

export function getRepositories(): Repositories {
  if (!instance) {
    if (import.meta.env.VITE_USE_MOCK === 'false') {
      throw new Error('HttpRepository 尚未接入，请保持 VITE_USE_MOCK=true');
    }
    instance = createMockRepository();
    if (import.meta.env.DEV) installMockHelpers();
  }
  return instance;
}

/** 全局单例（VGA 插座），UI 层统一从这里取 repository 实例 */
export const repo: Repositories = getRepositories();
