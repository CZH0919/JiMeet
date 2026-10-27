import type { Application, Conversation, Job, Message, Notification, Page, User } from '@/domain/models';
import type { Repositories } from '@/data/ports';
import { assertCanSubmit, db, DomainError, resetDb } from './db';
import type { ConversationRow } from './seed';

/** 模拟网络延迟，强制前端把 loading / 空态写对 */
function delay<T>(value: T, ms?: number): Promise<T> {
  const wait = ms ?? 300 + Math.random() * 300;
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), wait));
}

function currentUser(): User | null {
  const id = db.currentUserId;
  if (!id) return null;
  return db.users.find((u) => u.id === id) ?? null;
}

function paginate<T>(items: T[], page: number, pageSize: number): Page<T> {
  const start = (page - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    page,
    pageSize,
    total: items.length,
  };
}

function withMyStatus(job: Job, userId: string | null): Job {
  if (!userId) return { ...job, myApplicationStatus: null };
  const mine = db.applications.find(
    (a) => a.jobId === job.id && a.applicant.id === userId && a.status !== 'withdrawn',
  );
  return { ...job, myApplicationStatus: mine?.status ?? null };
}

function sortJobs(list: Job[], sort: 'latest' | 'earliest' = 'latest'): Job[] {
  const closedLast = (j: Job) => (j.status === 'closed' ? 1 : 0);
  return [...list].sort((a, b) => {
    if (closedLast(a) !== closedLast(b)) return closedLast(a) - closedLast(b);
    const ta = new Date(a.createdAt).getTime();
    const tb = new Date(b.createdAt).getTime();
    return sort === 'earliest' ? ta - tb : tb - ta;
  });
}

function notify(recipientId: string, n: Omit<Notification, 'id' | 'createdAt' | 'read' | 'recipientId'>) {
  db.pushNotification({ ...n, recipientId });
}

/** 库内会话（绝对参与者）→ 领域会话（当前用户视角的 peer + 最后一条消息） */
function toConversation(row: ConversationRow, viewerId: string): Conversation {
  const peerId = row.participantIds.find((id) => id !== viewerId) ?? viewerId;
  const u = db.users.find((x) => x.id === peerId);
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

export function createMockRepository(): Repositories {
  return {
    auth: {
      async login() {
        await delay(null, 600);
        // 统一身份认证：模拟返回默认学生
        const user = db.users.find((u) => u.id === '20230002')!;
        db.setCurrentUser(user.id);
        return user;
      },
      async loginWithEmail(email) {
        await delay(null, 400);
        const user = db.users.find((u) => u.email === email.trim());
        if (!user) throw new DomainError('邮箱或密码错误');
        db.setCurrentUser(user.id);
        return user;
      },
      async loginAs(userId) {
        await delay(null, 250);
        const user = db.users.find((u) => u.id === userId);
        if (!user) throw new DomainError('用户不存在');
        db.setCurrentUser(user.id);
        return user;
      },
      async logout() {
        db.setCurrentUser(null);
      },
      async getCurrentUser() {
        await delay(null, 80);
        return currentUser();
      },
    },

    jobs: {
      async list(q) {
        await delay(null);
        let list = db.jobs;
        if (q.type && q.type !== 'all') list = list.filter((j) => j.type === q.type);
        if (q.field && q.field !== 'all') list = list.filter((j) => j.field === q.field);
        if (q.minRecruit) list = list.filter((j) => j.recruitCount >= q.minRecruit!);
        if (q.deadlineWithin) {
          const limit = Date.now() + q.deadlineWithin * 86_400_000;
          list = list.filter((j) => new Date(j.deadline).getTime() <= limit);
        }
        if (q.keyword) {
          const kw = q.keyword.trim().toLowerCase();
          list = list.filter(
            (j) =>
              j.title.toLowerCase().includes(kw) ||
              j.description.toLowerCase().includes(kw) ||
              j.field.toLowerCase().includes(kw),
          );
        }
        list = sortJobs(list, q.sort);
        const uid = currentUser()?.id ?? null;
        return paginate(list.map((j) => withMyStatus(j, uid)), q.page, q.pageSize);
      },
      async detail(id) {
        await delay(null);
        const job = db.jobs.find((j) => j.id === id);
        if (!job) throw new DomainError('招聘不存在或已被删除');
        return withMyStatus(job, currentUser()?.id ?? null);
      },
      async create(input) {
        await delay(null);
        const user = currentUser();
        if (!user) throw new DomainError('请先登录');
        if (user.role === 'student' && input.type !== 'competition')
          throw new DomainError('学生仅可发布竞赛组队类招聘');
        if (user.role === 'teacher' && input.type !== 'campus_activity')
          throw new DomainError('教师仅可发布校内活动类招聘');
        const now = new Date().toISOString();
        const job: Job = {
          id: db.nextId('job'),
          type: input.type,
          title: input.title.trim(),
          description: input.description.trim(),
          requirement: input.requirement.trim(),
          field: input.field,
          recruitCount: input.recruitCount,
          acceptedCount: 0,
          deadline: input.deadline,
          status: 'open',
          publisher: { id: user.id, name: user.name, role: user.role },
          createdAt: now,
          updatedAt: now,
          applicationCount: 0,
        };
        db.jobs.unshift(job);
        db.save();
        return job;
      },
      async update(id, input) {
        await delay(null);
        const user = currentUser();
        const job = db.jobs.find((j) => j.id === id);
        if (!job) throw new DomainError('招聘不存在或已被删除');
        if (!user || job.publisher.id !== user.id) throw new DomainError('仅可编辑本人发布的招聘');
        job.type = input.type;
        job.title = input.title.trim();
        job.description = input.description.trim();
        job.requirement = input.requirement.trim();
        job.field = input.field;
        job.recruitCount = input.recruitCount;
        job.deadline = input.deadline;
        job.updatedAt = new Date().toISOString();
        // 修改后通知已申请者
        for (const a of db.applications.filter((a) => a.jobId === id)) {
          notify(a.applicant.id, {
            type: 'job_modified',
            title: `发布者修改了「${job.title}」的信息。`,
            body: '',
            jobId: job.id,
            jobTitle: job.title,
          });
        }
        db.save();
        return job;
      },
      async close(id) {
        await delay(null);
        const user = currentUser();
        const job = db.jobs.find((j) => j.id === id);
        if (!job) throw new DomainError('招聘不存在或已被删除');
        if (!user || job.publisher.id !== user.id) throw new DomainError('仅可关闭本人发布的招聘');
        job.status = 'closed';
        job.updatedAt = new Date().toISOString();
        db.save();
        return job;
      },
      async remove(id) {
        await delay(null);
        const user = currentUser();
        const job = db.jobs.find((j) => j.id === id);
        if (!job) throw new DomainError('招聘不存在或已被删除');
        if (!user || job.publisher.id !== user.id) throw new DomainError('仅可删除本人发布的招聘');
        const affected = db.applications.filter((a) => a.jobId === id);
        const result = {
          affectedPending: affected.filter((a) => a.status === 'pending').length,
          affectedAccepted: affected.filter((a) => a.status === 'accepted').length,
        };
        for (const a of affected) {
          notify(a.applicant.id, {
            type: 'job_removed_by_admin',
            title: `「${job.title}」已被发布者删除。`,
            body: '',
            jobId: job.id,
            jobTitle: job.title,
          });
        }
        db.setJobs(db.jobs.filter((j) => j.id !== id));
        db.setApplications(db.applications.filter((a) => a.jobId !== id));
        db.auditLogs.unshift({
          id: db.nextId('log'),
          operatorId: user.id,
          operatorName: user.name,
          operatorRole: user.role,
          targetType: 'job',
          targetId: id,
          targetTitle: job.title,
          action: 'delete_job',
          reason: '发布者删除本人招聘',
          createdAt: new Date().toISOString(),
        });
        db.save();
        return result;
      },
      async listMine(q) {
        await delay(null);
        const user = currentUser();
        if (!user) return paginate([], q.page, q.pageSize);
        const list = sortJobs(db.jobs.filter((j) => j.publisher.id === user.id), q.sort);
        return paginate(list.map((j) => withMyStatus(j, user.id)), q.page, q.pageSize);
      },
    },

    applications: {
      async submit({ jobId, resume, note }) {
        await delay(null);
        const user = currentUser();
        if (!user) throw new DomainError('请先登录');
        if (user.role !== 'student') throw new DomainError('仅学生可提交申请');
        const job = db.jobs.find((j) => j.id === jobId);
        if (!job) throw new DomainError('招聘不存在或已被删除');
        assertCanSubmit(job, user.id, db.applications);
        const now = new Date().toISOString();
        const application: Application = {
          id: db.nextId('app'),
          jobId: job.id,
          jobTitle: job.title,
          jobType: job.type,
          applicant: { id: user.id, name: user.name, role: user.role },
          resume,
          note: note?.trim() || undefined,
          status: 'pending',
          createdAt: now,
          updatedAt: now,
          resumeHidden: false,
        };
        db.applications.unshift(application);
        job.applicationCount += 1;
        db.save();
        return application;
      },
      async withdraw(applicationId) {
        await delay(null);
        const user = currentUser();
        const app = db.applications.find((a) => a.id === applicationId);
        if (!app) throw new DomainError('申请不存在');
        if (!user || app.applicant.id !== user.id) throw new DomainError('仅可撤回本人申请');
        if (app.status !== 'pending') throw new DomainError('该申请已进入终态，不可撤回');
        app.status = 'withdrawn';
        app.resumeHidden = true;
        app.updatedAt = new Date().toISOString();
        const job = db.jobs.find((j) => j.id === app.jobId);
        if (job) {
          notify(job.publisher.id, {
            type: 'application_withdrawn',
            title: `申请人已撤回对「${job.title}」的申请。`,
            body: '',
            jobId: job.id,
            jobTitle: job.title,
          });
        }
        db.save();
        return app;
      },
      async listMine(q) {
        await delay(null);
        const user = currentUser();
        if (!user) return paginate([], q.page, q.pageSize);
        const list = [...db.applications.filter((a) => a.applicant.id === user.id)].sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        );
        return paginate(list, q.page, q.pageSize);
      },
      async listForJob(jobId, q) {
        await delay(null);
        const user = currentUser();
        const job = db.jobs.find((j) => j.id === jobId);
        if (!job) throw new DomainError('招聘不存在或已被删除');
        if (!user || job.publisher.id !== user.id)
          throw new DomainError('仅发布者可查看申请列表');
        const list = [...db.applications.filter((a) => a.jobId === jobId)].sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        );
        return paginate(list, q.page, q.pageSize);
      },
      async mark(applicationId, action) {
        await delay(null);
        const user = currentUser();
        const app = db.applications.find((a) => a.id === applicationId);
        if (!app) throw new DomainError('申请不存在');
        const job = db.jobs.find((j) => j.id === app.jobId);
        if (!job) throw new DomainError('招聘不存在');
        if (!user || job.publisher.id !== user.id) throw new DomainError('仅发布者可处理申请');
        if (app.status !== 'pending') throw new DomainError('该申请已进入终态，不可再变更');

        if (action === 'hold') {
          // 暂留：状态保持处理中，仅发布者私有标记，不通知申请人
          return app;
        }

        if (action === 'accept') {
          if (job.acceptedCount >= job.recruitCount) {
            throw new DomainError('已满员，无法再确认');
          }
          app.status = 'accepted';
          app.updatedAt = new Date().toISOString();
          job.acceptedCount += 1;
          notify(app.applicant.id, {
            type: 'application_accepted',
            title: `你申请的「${job.title}」已被发布者接受。`,
            body: '',
            jobId: job.id,
            jobTitle: job.title,
          });
          // 满员瞬间：招聘自动满员，其余处理中申请自动拒绝
          if (job.acceptedCount >= job.recruitCount) {
            job.status = 'full';
            for (const other of db.applications.filter((a) => a.jobId === job.id && a.status === 'pending')) {
              other.status = 'rejected';
              other.updatedAt = new Date().toISOString();
              notify(other.applicant.id, {
                type: 'application_rejected',
                title: `你申请的「${job.title}」因已满员未通过筛选。`,
                body: '',
                jobId: job.id,
                jobTitle: job.title,
              });
            }
          }
        } else {
          // reject
          app.status = 'rejected';
          app.updatedAt = new Date().toISOString();
          notify(app.applicant.id, {
            type: 'application_rejected',
            title: `你申请的「${job.title}」未通过发布者筛选。`,
            body: '',
            jobId: job.id,
            jobTitle: job.title,
          });
        }
        db.save();
        return app;
      },
    },

    notifications: {
      async list(q) {
        await delay(null, 200);
        const uid = currentUser()?.id;
        const all = db.notifications.filter((n) => !uid || n.recipientId === uid);
        const list = [...all].sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        );
        return paginate(list, q.page, q.pageSize);
      },
      async markRead(id) {
        const n = db.notifications.find((x) => x.id === id);
        if (n) n.read = true;
        db.save();
      },
      async markAllRead() {
        for (const n of db.notifications) n.read = true;
        db.save();
      },
      async unreadCount() {
        await delay(null, 120);
        const uid = currentUser()?.id;
        return db.notifications.filter((n) => !n.read && (!uid || n.recipientId === uid)).length;
      },
    },

    admin: {
      async listAllJobs(q) {
        await delay(null);
        const list = sortJobs(db.jobs, q.sort);
        return paginate(list.map((j) => withMyStatus(j, currentUser()?.id ?? null)), q.page, q.pageSize);
      },
      async removeJobWithReason(jobId, reason) {
        await delay(null);
        const user = currentUser();
        if (!user || !user.isAdmin) throw new DomainError('无管理员权限');
        const job = db.jobs.find((j) => j.id === jobId);
        if (!job) throw new DomainError('招聘不存在或已被删除');
        const affected = db.applications.filter((a) => a.jobId === jobId);
        for (const a of affected) {
          notify(a.applicant.id, {
            type: 'job_removed_by_admin',
            title: `「${job.title}」因不合规已被管理员删除。`,
            body: '',
            jobId: job.id,
            jobTitle: job.title,
          });
        }
        notify(job.publisher.id, {
          type: 'job_removed_by_admin',
          title: `你发布的「${job.title}」因不合规已被管理员删除。`,
          body: '',
          jobId: job.id,
          jobTitle: job.title,
        });
        db.setJobs(db.jobs.filter((j) => j.id !== jobId));
        db.setApplications(db.applications.filter((a) => a.jobId !== jobId));
        db.auditLogs.unshift({
          id: db.nextId('log'),
          operatorId: user.id,
          operatorName: user.name,
          operatorRole: user.role,
          targetType: 'job',
          targetId: jobId,
          targetTitle: job.title,
          action: 'delete_job',
          reason,
          createdAt: new Date().toISOString(),
        });
        db.save();
      },
      async listAuditLogs(q) {
        await delay(null, 200);
        const list = [...db.auditLogs].sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        );
        return paginate(list, q.page, q.pageSize);
      },
    },

    messages: {
      async listConversations(q) {
        await delay(null, 200);
        const user = currentUser();
        if (!user) return paginate([], q.page, q.pageSize);
        const list = db.conversations
          .filter((c) => c.participantIds.includes(user.id))
          .map((c) => toConversation(c, user.id))
          .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
        return paginate(list, q.page, q.pageSize);
      },

      async listMessages(conversationId, q) {
        await delay(null, 200);
        const user = currentUser();
        if (!user) throw new DomainError('请先登录');
        const conv = db.conversations.find((c) => c.id === conversationId);
        if (!conv) throw new DomainError('会话不存在');
        if (!conv.participantIds.includes(user.id)) throw new DomainError('无权查看该会话');
        const list = db.messages
          .filter((m) => m.conversationId === conversationId)
          .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
        return paginate(list, q.page, q.pageSize);
      },

      async send(conversationId, text) {
        await delay(null, 150);
        const user = currentUser();
        if (!user) throw new DomainError('请先登录');
        const conv = db.conversations.find((c) => c.id === conversationId);
        if (!conv) throw new DomainError('会话不存在');
        if (!conv.participantIds.includes(user.id)) throw new DomainError('无权在该会话发言');
        const body = text.trim();
        if (!body) throw new DomainError('消息不能为空');
        if (body.length > 1000) throw new DomainError('单条消息不超过 1000 字');
        const message: Message = {
          id: db.nextId('msg'),
          conversationId,
          senderId: user.id,
          text: body,
          createdAt: new Date().toISOString(),
        };
        db.messages.push(message);
        conv.updatedAt = message.createdAt;
        db.save();
        return message;
      },

      async openWith(userId) {
        await delay(null, 200);
        const user = currentUser();
        if (!user) throw new DomainError('请先登录');
        if (userId === user.id) throw new DomainError('不能与自己发起会话');
        if (!db.users.some((u) => u.id === userId)) throw new DomainError('用户不存在');
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

    files: {
      async uploadResume(file, onProgress) {
        // 模拟分片上传进度
        for (let i = 1; i <= 5; i++) {
          onProgress?.(i / 5);
          await new Promise((r) => setTimeout(r, 120));
        }
        return {
          id: db.nextId('resume'),
          fileName: file.name,
          size: file.size,
          mimeType: file.type || 'application/pdf',
          uploadedAt: new Date().toISOString(),
          downloadUrl: `mock://resume/${file.name}`,
        };
      },
    },
  };
}

/** 演示辅助：暴露到 window 便于控制台切换场景 */
export function installMockHelpers() {
  const w = window as unknown as { __mock?: Record<string, unknown> };
  w.__mock = {
    reset: () => {
      resetDb();
      return '已重置';
    },
    users: () => db.users,
  };
}
