import { ArrowLeft } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import type { AnnouncementTimeKind } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { formatDateTime, fromLocalInputValue, toLocalInputValue } from '@/domain/format';
import { JOB_STATUS_LABEL } from '@/domain/labels';
import {
  validateAnnouncementForm,
  type AnnouncementInput,
  type FieldErrors,
} from '@/domain/validation';
import { Button } from '@/components/ui/Button';
import { Field, Input, Select, Textarea } from '@/components/ui/Field';
import { ErrorState, InfoBanner, PageLoader } from '@/components/ui/Feedback';
import { toast } from '@/stores/toast';
import { clsx } from 'clsx';

const EMPTY: AnnouncementInput = {
  title: '',
  content: '',
  timeKind: 'deadline',
  eventAt: '',
  linkUrl: '',
  recruitmentId: null,
};

export function AnnouncementFormPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = !!id;
  const { user } = useAuth();
  const navigate = useNavigate();

  const { data: existing, loading, error } = useAsync(
    () => (id ? repo.announcements.detail(id) : Promise.resolve(null)),
    [id],
  );
  const recruitments = useAsync(
    () => repo.jobs.list({ type: 'all', page: 1, pageSize: 50 }),
    [],
  );

  const [form, setForm] = useState<AnnouncementInput>(EMPTY);
  const [errors, setErrors] = useState<FieldErrors<AnnouncementInput>>({});
  const [submitting, setSubmitting] = useState(false);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!existing || initialized) return;
    setForm({
      title: existing.title,
      content: existing.content,
      timeKind: existing.timeKind,
      eventAt: existing.eventAt,
      linkUrl: existing.linkUrl ?? '',
      recruitmentId: existing.recruitmentId ? Number(existing.recruitmentId) : null,
    });
    setInitialized(true);
  }, [existing, initialized]);

  if (!user?.isAdmin) return <ErrorState message="仅管理员可发布或编辑公告" />;
  if (loading) return <PageLoader />;
  if (isEdit && error) return <ErrorState message={error} />;
  if (isEdit && existing && !existing.permissions.canEdit) {
    return <ErrorState message="仅公告作者本人可编辑该公告" />;
  }

  const set = <K extends keyof AnnouncementInput>(k: K, v: AnnouncementInput[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    const errs = validateAnnouncementForm(form);
    setErrors(errs);
    if (Object.keys(errs).length > 0) {
      toast.error('请检查表单中的错误项');
      return;
    }
    setSubmitting(true);
    try {
      const created = isEdit
        ? await repo.announcements.update(id!, form)
        : await repo.announcements.create(form);
      toast.success(isEdit ? '公告已更新' : '公告已发布');
      navigate(`/announcements/${created.id}`, { replace: true });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page-shell max-w-[820px] py-8 sm:py-10">
      <Link
        to={isEdit ? `/announcements/${id}` : '/'}
        className="mb-4 inline-flex items-center gap-1 text-sm text-ink2 transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} /> {isEdit ? '返回公告详情' : '返回首页'}
      </Link>

      <h1 className="text-xl font-bold text-ink">{isEdit ? '编辑公告' : '发布公告'}</h1>
      <p className="mt-1 text-sm text-ink2">发布竞赛报名、活动安排等校内信息，展示在首页。</p>

      <div className="mt-5">
        <InfoBanner>公告仅作信息展示；如需招募成员，请发布招聘。</InfoBanner>
      </div>

      <div className="panel mt-5 flex flex-col gap-5 px-6 py-6">
        <Field label="公告标题" required error={errors.title} hint="1～100 字">
          <Input
            value={form.title}
            onChange={(e) => set('title', e.target.value)}
            placeholder="如：全国大学生数学建模竞赛校内报名通知"
            invalid={!!errors.title}
            maxLength={100}
          />
        </Field>

        <Field label="时间类型" required error={errors.timeKind}>
          <div className="flex gap-2">
            {(['deadline', 'event'] as AnnouncementTimeKind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => set('timeKind', k)}
                className={clsx(
                  'rounded-md px-4 py-2 text-sm transition-colors',
                  form.timeKind === k
                    ? 'bg-primary-soft font-medium text-primary'
                    : 'border border-line text-ink2 hover:border-primary/40 hover:text-primary',
                )}
              >
                {k === 'deadline' ? '报名截止时间' : '活动时间'}
              </button>
            ))}
          </div>
        </Field>

        <Field label="具体时间" required error={errors.eventAt} hint="允许填写已过去的时间">
          <Input
            type="datetime-local"
            value={form.eventAt ? toLocalInputValue(form.eventAt) : ''}
            onChange={(e) => set('eventAt', fromLocalInputValue(e.target.value))}
            invalid={!!errors.eventAt}
          />
        </Field>

        <Field label="公告内容" required error={errors.content} hint="纯文本，1～5000 字">
          <Textarea
            value={form.content}
            onChange={(e) => set('content', e.target.value)}
            placeholder="填写竞赛/活动名称、报名方式、组织单位、注意事项等信息"
            invalid={!!errors.content}
            className="min-h-[180px]"
            maxLength={5000}
          />
          <div className="text-right text-xs text-muted">{form.content.length}/5000</div>
        </Field>

        <Field label="相关链接（选填）" error={errors.linkUrl} hint="仅支持 http:// 或 https:// 地址">
          <Input
            value={form.linkUrl}
            onChange={(e) => set('linkUrl', e.target.value)}
            placeholder="https://example.com/notice"
            invalid={!!errors.linkUrl}
            maxLength={500}
          />
        </Field>

        <Field label="关联招聘（选填）" error={errors.recruitmentId} hint="关联后公告详情可跳转到对应招聘">
          <Select
            value={form.recruitmentId ?? ''}
            onChange={(e) => set('recruitmentId', e.target.value ? Number(e.target.value) : null)}
            invalid={!!errors.recruitmentId}
          >
            <option value="">不关联</option>
            {(recruitments.data?.items ?? []).map((job) => (
              <option key={job.id} value={job.id}>
                {job.title}（{JOB_STATUS_LABEL[job.status]} · {formatDateTime(job.deadline)} 截止）
              </option>
            ))}
          </Select>
        </Field>

        <div className="flex justify-end gap-3 border-t border-line pt-5">
          <Button variant="secondary" onClick={() => navigate(-1)}>
            取消
          </Button>
          <Button onClick={submit} loading={submitting}>
            {isEdit ? '保存修改' : '发布公告'}
          </Button>
        </div>
      </div>
    </div>
  );
}
