import type {
  Application,
  Job,
  JobQuery,
  Notification,
  Page,
  Tag,
  User,
} from '@/domain/models';
import type { Repositories } from '@/data/ports';
import type { CreateJobInput } from '@/domain/validation';
import { ApiError, downloadResume, fetchCsrf, http, setCsrfToken } from './client';
import {
  mapApplication,
  mapApplicationPage,
  mapNotificationPage,
  mapRecruitmentDetail,
  mapRecruitmentPage,
  mapTagList,
  mapUser,
} from './mappers';

type HttpRepositories = Omit<Repositories, 'messages'>;

function toRecruitmentQuery(q: JobQuery): Record<string, string | number | undefined> {
  return {
    q: q.keyword?.trim() || undefined,
    type: q.type && q.type !== 'all' ? q.type : undefined,
    tag: q.tagId ?? undefined,
    status: q.status ?? undefined,
    page: q.page,
    page_size: q.pageSize,
  };
}

function toRecruitmentBody(input: CreateJobInput): Record<string, unknown> {
  return {
    title: input.title.trim(),
    type: input.type,
    description: input.description.trim(),
    tag_ids: input.tags.map((t) => t.id),
    ...(input.minHeadcount == null ? {} : { min_headcount: input.minHeadcount }),
    max_headcount: input.maxHeadcount,
    deadline: input.deadline,
  };
}

export function createHttpRepository(): HttpRepositories {
  return {
    auth: {
      async devLogin(realId: string): Promise<User> {
        await fetchCsrf();
        const data = await http.post<Record<string, unknown>>('/auth/dev-login', { real_id: realId });
        await fetchCsrf(); // 登录成功轮换 CSRF 密钥
        return mapUser(data);
      },
      async logout(): Promise<void> {
        try {
          await http.post('/auth/logout');
        } finally {
          setCsrfToken(null);
        }
      },
      async getCurrentUser(): Promise<User | null> {
        try {
          // 恢复会话前先取得 CSRF 令牌：刷新页面后内存中的令牌已丢失，
          // 若 sessionid 仍有效却直接发起写请求，会因缺少 X-CSRFToken 被后端以 403 FORBIDDEN 拒绝。
          await fetchCsrf();
          const data = await http.get<Record<string, unknown>>('/me');
          return mapUser(data);
        } catch (e) {
          if (e instanceof ApiError && e.status === 401) return null;
          throw e;
        }
      },
      async confirmPrivacyConsent(): Promise<User> {
        const data = await http.post<Record<string, unknown>>('/me/privacy-consent');
        return mapUser(data);
      },
    },

    jobs: {
      async listTags(): Promise<Tag[]> {
        const data = await http.get<Record<string, unknown>>('/tags');
        return mapTagList(data);
      },
      async list(q: JobQuery): Promise<Page<Job>> {
        const data = await http.get<Record<string, unknown>>('/recruitments', toRecruitmentQuery(q));
        return mapRecruitmentPage(data);
      },
      async detail(id: string): Promise<Job> {
        const data = await http.get<Record<string, unknown>>(`/recruitments/${id}`);
        return mapRecruitmentDetail(data);
      },
      async create(input: CreateJobInput): Promise<Job> {
        const data = await http.post<Record<string, unknown>>('/recruitments', toRecruitmentBody(input));
        return mapRecruitmentDetail(data);
      },
      async update(id: string, input: CreateJobInput): Promise<Job> {
        const data = await http.patch<Record<string, unknown>>(`/recruitments/${id}`, toRecruitmentBody(input));
        return mapRecruitmentDetail(data);
      },
      async close(id: string): Promise<Job> {
        const data = await http.post<Record<string, unknown>>(`/recruitments/${id}/close`, {});
        return mapRecruitmentDetail(data);
      },
      async remove(id: string, reason?: string): Promise<void> {
        await http.del(`/recruitments/${id}`, reason ? { reason } : {});
      },
      async listMine(q: JobQuery): Promise<Page<Job>> {
        const data = await http.get<Record<string, unknown>>('/me/recruitments', toRecruitmentQuery(q));
        return mapRecruitmentPage(data);
      },
    },

    applications: {
      async submit(input: { jobId: string; resumeFile: File; note?: string }): Promise<Application> {
        const form = new FormData();
        form.append('resume', input.resumeFile);
        form.append('note', input.note?.trim() ?? '');
        const data = await http.postForm<Record<string, unknown>>(
          `/recruitments/${input.jobId}/applications`,
          form,
        );
        return mapApplication(data);
      },
      async detail(applicationId: string): Promise<Application> {
        const data = await http.get<Record<string, unknown>>(`/applications/${applicationId}`);
        return mapApplication(data);
      },
      async update(applicationId: string, input: { resumeFile?: File; note?: string }): Promise<Application> {
        const form = new FormData();
        if (input.resumeFile) form.append('resume', input.resumeFile);
        if (input.note !== undefined) form.append('note', input.note.trim());
        const data = await http.patchForm<Record<string, unknown>>(`/applications/${applicationId}`, form);
        return mapApplication(data);
      },
      async withdraw(applicationId: string): Promise<Application> {
        const data = await http.post<Record<string, unknown>>(`/applications/${applicationId}/withdraw`, {});
        return mapApplication(data);
      },
      async listMine(q: { page: number; pageSize: number }): Promise<Page<Application>> {
        const data = await http.get<Record<string, unknown>>('/me/applications', {
          page: q.page,
          page_size: q.pageSize,
        });
        return mapApplicationPage(data);
      },
      async listForJob(jobId: string, q: { page: number; pageSize: number }): Promise<Page<Application>> {
        const data = await http.get<Record<string, unknown>>(`/recruitments/${jobId}/applications`, {
          page: q.page,
          page_size: q.pageSize,
        });
        return mapApplicationPage(data);
      },
      async mark(applicationId: string, action: 'accept' | 'hold' | 'reject'): Promise<Application> {
        const path = `/applications/${applicationId}/${action}`;
        const data = await http.post<Record<string, unknown>>(path, {});
        return mapApplication(data);
      },
      async clearModified(applicationId: string, seenUpdatedAt: string): Promise<void> {
        await http.post(`/applications/${applicationId}/read`, { seen_updated_at: seenUpdatedAt });
      },
      async downloadResume(applicationId: string): Promise<void> {
        await downloadResume(applicationId);
      },
    },

    notifications: {
      async list(q: { page: number; pageSize: number }): Promise<Page<Notification>> {
        const data = await http.get<Record<string, unknown>>('/notifications', {
          page: q.page,
          page_size: q.pageSize,
        });
        return mapNotificationPage(data);
      },
      async markRead(id: string): Promise<void> {
        await http.post(`/notifications/${id}/read`, {});
      },
      async markAllRead(): Promise<void> {
        await http.post('/notifications/read-all', {});
      },
      async unreadCount(): Promise<number> {
        const data = await http.get<{ unread_count: number }>('/notifications/unread-count');
        return Number(data.unread_count ?? 0);
      },
    },

    admin: {
      async listAllJobs(q: JobQuery): Promise<Page<Job>> {
        const data = await http.get<Record<string, unknown>>('/recruitments', toRecruitmentQuery(q));
        return mapRecruitmentPage(data);
      },
      async removeJobWithReason(jobId: string, reason: string): Promise<void> {
        await http.del(`/recruitments/${jobId}`, { reason });
      },
    },
  };
}
