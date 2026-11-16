import type {
  Announcement,
  Application,
  Job,
  JobQuery,
  Notification,
  Page,
  Tag,
  User,
} from '@/domain/models';
import type { Repositories } from '@/data/ports';
import type { AnnouncementInput, CreateJobInput, LoginInput, RegisterInput } from '@/domain/validation';
import { ApiError, downloadResumeFile, fetchCsrf, http, setCsrfToken } from './client';
import {
  mapAnnouncement,
  mapAnnouncementPage,
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
    min_headcount: input.minHeadcount,
    max_headcount: input.maxHeadcount,
    deadline: input.deadline,
  };
}

function toAnnouncementBody(input: AnnouncementInput): Record<string, unknown> {
  return {
    title: input.title.trim(),
    content: input.content.trim(),
    time_kind: input.timeKind,
    event_at: input.eventAt,
    link_url: input.linkUrl.trim() ? input.linkUrl.trim() : null,
    recruitment_id: input.recruitmentId,
  };
}

export function createHttpRepository(): HttpRepositories {
  return {
    auth: {
      async register(input: RegisterInput): Promise<User> {
        await fetchCsrf();
        const body: Record<string, unknown> = {
          email: input.email.trim().toLowerCase(),
          password: input.password,
          name: input.name.trim(),
          role: input.role,
        };
        if (input.nickname.trim()) body.nickname = input.nickname.trim();
        const data = await http.post<Record<string, unknown>>('/auth/register', body);
        await fetchCsrf(); // 登录成功会轮换会话键与 CSRF 令牌
        return mapUser(data);
      },
      async login(input: LoginInput): Promise<User> {
        await fetchCsrf();
        const data = await http.post<Record<string, unknown>>('/auth/login', {
          email: input.email.trim().toLowerCase(),
          password: input.password,
        });
        await fetchCsrf();
        return mapUser(data);
      },
      async devLogin(realId: string): Promise<User> {
        await fetchCsrf();
        const data = await http.post<Record<string, unknown>>('/auth/dev-login', {
          real_id: realId.trim(),
        });
        await fetchCsrf();
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
        // 刷新页面后内存中的 CSRF 令牌已丢失，先取一次再读 /me，
        // 否则后续写请求会因缺少 X-CSRFToken 被后端以 403 拒绝。
        await fetchCsrf();
        try {
          const data = await http.get<Record<string, unknown>>('/me');
          return mapUser(data);
        } catch (e) {
          if (e instanceof ApiError && (e.status === 401 || e.code === 'UNAUTHENTICATED')) return null;
          throw e;
        }
      },
      async updateProfile(input: { nickname: string }): Promise<User> {
        const data = await http.patch<Record<string, unknown>>('/me', { nickname: input.nickname.trim() });
        return mapUser(data);
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
        const data = await http.patch<Record<string, unknown>>(
          `/recruitments/${id}`,
          toRecruitmentBody(input),
        );
        return mapRecruitmentDetail(data);
      },
      async close(id: string): Promise<Job> {
        const data = await http.post<Record<string, unknown>>(`/recruitments/${id}/close`, {});
        return mapRecruitmentDetail(data);
      },
      async remove(id: string, reason?: string): Promise<void> {
        await http.del(`/recruitments/${id}`, reason?.trim() ? { reason: reason.trim() } : {});
      },
      async listMine(q: JobQuery): Promise<Page<Job>> {
        const data = await http.get<Record<string, unknown>>('/me/recruitments', toRecruitmentQuery(q));
        return mapRecruitmentPage(data);
      },
    },

    announcements: {
      async list(q: { page: number; pageSize: number }): Promise<Page<Announcement>> {
        const data = await http.get<Record<string, unknown>>('/announcements', {
          page: q.page,
          page_size: q.pageSize,
        });
        return mapAnnouncementPage(data);
      },
      async detail(id: string): Promise<Announcement> {
        const data = await http.get<Record<string, unknown>>(`/announcements/${id}`);
        return mapAnnouncement(data);
      },
      async create(input: AnnouncementInput): Promise<Announcement> {
        const data = await http.post<Record<string, unknown>>('/announcements', toAnnouncementBody(input));
        return mapAnnouncement(data);
      },
      async update(id: string, input: AnnouncementInput): Promise<Announcement> {
        const data = await http.patch<Record<string, unknown>>(
          `/announcements/${id}`,
          toAnnouncementBody(input),
        );
        return mapAnnouncement(data);
      },
      async removeOwn(id: string): Promise<void> {
        await http.del(`/announcements/${id}`);
      },
      async governRemove(id: string, reason: string): Promise<void> {
        await http.del(`/admin/announcements/${id}`, { reason: reason.trim() });
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
      async update(
        applicationId: string,
        input: { resumeFile?: File; note?: string },
      ): Promise<Application> {
        const form = new FormData();
        if (input.resumeFile) form.append('resume', input.resumeFile);
        if (input.note !== undefined) form.append('note', input.note.trim());
        const data = await http.patchForm<Record<string, unknown>>(
          `/applications/${applicationId}`,
          form,
        );
        return mapApplication(data);
      },
      async withdraw(applicationId: string): Promise<Application> {
        const data = await http.post<Record<string, unknown>>(
          `/applications/${applicationId}/withdraw`,
          {},
        );
        return mapApplication(data);
      },
      async listMine(q: { page: number; pageSize: number; status?: string }): Promise<Page<Application>> {
        const data = await http.get<Record<string, unknown>>('/me/applications', {
          page: q.page,
          page_size: q.pageSize,
          status: q.status,
        });
        return mapApplicationPage(data);
      },
      async listForJob(
        jobId: string,
        q: { page: number; pageSize: number; status?: string },
      ): Promise<Page<Application>> {
        const data = await http.get<Record<string, unknown>>(`/recruitments/${jobId}/applications`, {
          page: q.page,
          page_size: q.pageSize,
          status: q.status,
        });
        return mapApplicationPage(data);
      },
      async mark(
        applicationId: string,
        action: 'accept' | 'hold' | 'reject' | 'unhold',
      ): Promise<Application> {
        const data = await http.post<Record<string, unknown>>(
          `/applications/${applicationId}/${action}`,
          {},
        );
        return mapApplication(data);
      },
      async clearModified(applicationId: string, seenUpdatedAt: string): Promise<void> {
        await http.post(`/applications/${applicationId}/read`, { seen_updated_at: seenUpdatedAt });
      },
      async downloadResume(applicationId: string): Promise<void> {
        await downloadResumeFile(applicationId);
      },
    },

    notifications: {
      async list(q: { page: number; pageSize: number; isRead?: boolean }): Promise<Page<Notification>> {
        const data = await http.get<Record<string, unknown>>('/notifications', {
          page: q.page,
          page_size: q.pageSize,
          is_read: q.isRead,
        });
        return mapNotificationPage(data);
      },
      async markRead(id: string): Promise<void> {
        await http.post(`/notifications/${id}/read`, {});
      },
      async markAllRead(): Promise<number> {
        const data = await http.post<{ updated_count: number }>('/notifications/read-all', {});
        return Number(data?.updated_count ?? 0);
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
      async governRemoveJob(jobId: string, reason: string): Promise<void> {
        await http.del(`/admin/recruitments/${jobId}`, { reason: reason.trim() });
      },
    },
  };
}
