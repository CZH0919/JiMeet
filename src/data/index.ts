import type { Job } from '@/domain/models';
import type { Repositories } from './ports';
import { createHttpRepository } from './http/repository';
import { createLocalRepository } from './mock/repository';

/**
 * 混合仓储（依赖注入的唯一开关）：
 * - 招聘 / 申请 / 通知 / 个人资料 / 标签 / 管理员 → 后端 HTTP（data/http）
 * - 竞赛通知 / 站内聊天（后端暂未提供）→ 本地 mock（data/mock）
 *
 * UI 层统一从 `repo` 取实例，不感知底层来源。
 */

function isNoticeId(id: string): boolean {
  return id.startsWith('notice-');
}

let instance: Repositories | null = null;

export function getRepositories(): Repositories {
  if (!instance) {
    const http = createHttpRepository();
    const local = createLocalRepository();

    const jobs: Repositories['jobs'] = {
      listTags: http.jobs.listTags,

      async list(q) {
        // 竞赛通知走本地；其余（含「全部」）走后端列表
        if (q.type === 'competition_notice') return local.jobs.list(q);
        return http.jobs.list(q);
      },

      async listMine(q) {
        if (q.type === 'competition_notice') return local.jobs.listMine(q);
        // 「我发布的」= 后端招聘 + 本地竞赛通知（个人中心按类型拆分展示）
        const [backend, notices] = await Promise.all([
          http.jobs.listMine(q),
          local.jobs.listMine({ ...q, type: 'competition_notice' }),
        ]);
        const items: Job[] = [...backend.items, ...notices.items].sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        );
        return { items, page: q.page, pageSize: q.pageSize, total: backend.total + notices.total };
      },

      detail(id) {
        return isNoticeId(id) ? local.jobs.detail(id) : http.jobs.detail(id);
      },
      create(input) {
        return input.type === 'competition_notice' ? local.jobs.create(input) : http.jobs.create(input);
      },
      update(id, input) {
        return isNoticeId(id) ? local.jobs.update(id, input) : http.jobs.update(id, input);
      },
      close(id) {
        return isNoticeId(id) ? local.jobs.close(id) : http.jobs.close(id);
      },
      remove(id, reason) {
        return isNoticeId(id) ? local.jobs.remove(id) : http.jobs.remove(id, reason);
      },
    };

    const auth: Repositories['auth'] = {
      async devLogin(realId) {
        const u = await http.auth.devLogin(realId);
        local.setCurrentUser({ id: u.id, name: u.name, role: u.role });
        return u;
      },
      async logout() {
        await http.auth.logout();
        local.setCurrentUser(null);
      },
      async getCurrentUser() {
        const u = await http.auth.getCurrentUser();
        local.setCurrentUser(u ? { id: u.id, name: u.name, role: u.role } : null);
        return u;
      },
      async confirmPrivacyConsent() {
        const u = await http.auth.confirmPrivacyConsent();
        local.setCurrentUser({ id: u.id, name: u.name, role: u.role });
        return u;
      },
    };

    instance = {
      auth,
      jobs,
      applications: http.applications,
      notifications: http.notifications,
      admin: http.admin,
      messages: local.messages,
    };
  }
  return instance;
}

/** 全局单例，UI 层统一从这里取 repository 实例 */
export const repo: Repositories = getRepositories();
