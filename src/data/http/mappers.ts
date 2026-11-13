import type {
  Application,
  ApplicationStatus,
  Job,
  JobStatus,
  JobType,
  Notification,
  NotificationType,
  Page,
  Tag,
  User,
  UserRole,
} from '@/domain/models';
import { describeCode } from './client';

/** 后端 DTO → 领域模型映射。字段改名、枚举查表、兜底默认值都集中在这里。 */

type Json = Record<string, unknown>;

function str(v: unknown): string {
  return v == null ? '' : String(v);
}

function mapRole(v: unknown): UserRole {
  return v === 'teacher' ? 'teacher' : 'student';
}

function mapPublicUser(v: Json | undefined): Job['publisher'] {
  return {
    id: str(v?.uid),
    name: str(v?.nickname ?? v?.name ?? '未知用户'),
    role: mapRole(v?.role),
  };
}

function mapJobType(v: unknown): JobType {
  if (v === 'competition' || v === 'activity' || v === 'internship') return v;
  return 'activity';
}

function mapJobStatus(v: unknown): JobStatus {
  if (v === 'full') return 'full';
  if (v === 'closed') return 'closed';
  return 'open';
}

function mapApplicationStatus(v: unknown): ApplicationStatus {
  switch (v) {
    case 'accepted':
      return 'accepted';
    case 'rejected':
      return 'rejected';
    case 'withdrawn':
      return 'withdrawn';
    case 'invalid':
      return 'invalid';
    default:
      return 'processing';
  }
}

function mapTags(v: unknown): Tag[] {
  if (!Array.isArray(v)) return [];
  return v.map((t) => ({ id: Number((t as Json)?.id ?? 0), name: str((t as Json)?.name) }));
}

function mapPage<T>(items: T[], data: Json): Page<T> {
  return {
    items,
    page: Number(data.page ?? 1),
    pageSize: Number(data.page_size ?? items.length),
    total: Number(data.total ?? items.length),
  };
}

export function mapUser(raw: Json): User {
  return {
    id: str(raw.uid),
    name: str(raw.nickname ?? raw.name),
    role: mapRole(raw.role),
    isAdmin: raw.is_admin === true,
    email: raw.email == null ? undefined : str(raw.email),
    privacyConsented: raw.privacy_consented === true,
  };
}

/** 列表摘要（无 description / my_application / permissions） */
export function mapRecruitmentSummary(raw: Json): Job {
  return {
    id: str(raw.id),
    type: mapJobType(raw.type),
    title: str(raw.title),
    description: '',
    tags: mapTags(raw.tags),
    minHeadcount: raw.min_headcount == null ? null : Number(raw.min_headcount),
    maxHeadcount: Number(raw.max_headcount ?? 0),
    acceptedCount: Number(raw.accepted_count ?? 0),
    deadline: str(raw.deadline),
    status: mapJobStatus(raw.status),
    isDeleted: raw.is_deleted === true,
    publisher: mapPublicUser(raw.publisher as Json | undefined),
    createdAt: str(raw.created_at),
    updatedAt: str(raw.updated_at),
    applicationCount: 0,
  };
}

/** 详情（含 description / my_application / permissions / application_counts） */
export function mapRecruitmentDetail(raw: Json): Job {
  const summary = mapRecruitmentSummary(raw);
  const myApplication = raw.my_application as Json | null | undefined;
  const permissions = raw.permissions as Json | undefined;
  const counts = raw.application_counts as Json | undefined;
  let applicationCount = 0;
  if (counts) {
    for (const k of Object.keys(counts)) applicationCount += Number((counts as Json)[k] ?? 0);
  }
  return {
    ...summary,
    description: str(raw.description),
    myApplicationStatus: myApplication ? mapApplicationStatus(myApplication.status) : null,
    applicationCount,
    permissions: {
      canApply: permissions?.can_apply === true,
      canEdit: permissions?.can_edit === true,
      canClose: permissions?.can_close === true,
      canDelete: permissions?.can_delete === true,
      canViewApplications: permissions?.can_view_applications === true,
      applyBlockedReason: permissions?.apply_blocked_reason
        ? describeCode(str(permissions.apply_blocked_reason))
        : null,
      applyBlockedCode: permissions?.apply_blocked_reason
        ? str(permissions.apply_blocked_reason)
        : null,
    },
  };
}

export function mapApplication(raw: Json): Application {
  const recruitment = raw.recruitment as Json | undefined;
  const applicant = raw.applicant as Json | undefined;
  const resume = raw.resume as Json | null | undefined;
  const permissions = raw.permissions as Json | undefined;
  return {
    id: str(raw.id),
    jobId: str(recruitment?.id),
    jobTitle: str(recruitment?.title),
    jobType: mapJobType(recruitment?.type),
    applicant: {
      id: str(applicant?.uid),
      name: str(applicant?.name ?? applicant?.nickname ?? '未知用户'),
      role: mapRole(applicant?.role),
    },
    resume: resume
      ? { fileName: str(resume.name), size: Number(resume.size ?? 0), type: str(resume.type) }
      : null,
    note: raw.note == null ? undefined : str(raw.note),
    status: mapApplicationStatus(raw.status),
    createdAt: str(raw.created_at),
    updatedAt: str(raw.updated_at),
    publisherMark: raw.publisher_mark === 'hold' ? 'hold' : 'none',
    modified: raw.has_unseen_update === true,
    canModify: permissions?.can_modify === true,
    canWithdraw: permissions?.can_withdraw === true,
    canProcess: permissions?.can_process === true,
    canDownloadResume: permissions?.can_download_resume === true,
  };
}

const NOTIFICATION_TYPES: Record<string, NotificationType> = {
  application_submitted: 'application_submitted',
  application_accepted: 'application_accepted',
  application_rejected: 'application_rejected',
  application_withdrawn: 'application_withdrawn',
  application_updated: 'application_updated',
  recruitment_closed: 'recruitment_closed',
  recruitment_updated: 'recruitment_updated',
  recruitment_deleted: 'recruitment_deleted',
  admin_removed: 'admin_removed',
};

export function mapNotification(raw: Json): Notification {
  const type = NOTIFICATION_TYPES[str(raw.type)] ?? 'recruitment_updated';
  return {
    id: str(raw.id),
    type,
    title: str(raw.title),
    body: str(raw.content),
    jobId: raw.recruitment_id == null ? undefined : str(raw.recruitment_id),
    applicationId: raw.application_id == null ? undefined : str(raw.application_id),
    createdAt: str(raw.created_at),
    read: raw.is_read === true,
  };
}

export function mapTagList(data: Json): Tag[] {
  return mapTags(data.items);
}

export function mapRecruitmentPage(data: Json): Page<Job> {
  const items = Array.isArray(data.items) ? data.items.map((r) => mapRecruitmentSummary(r as Json)) : [];
  return mapPage(items, data);
}

export function mapApplicationPage(data: Json): Page<Application> {
  const items = Array.isArray(data.items) ? data.items.map((r) => mapApplication(r as Json)) : [];
  return mapPage(items, data);
}

export function mapNotificationPage(data: Json): Page<Notification> {
  const items = Array.isArray(data.items) ? data.items.map((r) => mapNotification(r as Json)) : [];
  return mapPage(items, data);
}
