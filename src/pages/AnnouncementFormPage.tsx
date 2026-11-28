import { ArrowLeft } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
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
import { InfoBanner, PageLoader } from '@/components/ui/Feedback';
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

/**
 * 发布公告 / 投稿公告。
 * 管理员直接发布（跳过审核，可关联招聘）；普通用户提交待审稿，提交后不能改稿、撤回。
 * 公告不支持编辑，后端对 PATCH 返回 405。
 */
export function AnnouncementFormPage() {
  const { user, ready } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.isAdmin === true;

  const recruitments = useAsync(
    () => (isAdmin ? repo.jobs.list({ type: 'all', page: 1, pageSize: 50 }) : Promise.resolve(null)),
    [isAdmin],
  );

  const [form, setForm] = useState<AnnouncementInput>(EMPTY);
  const [errors, setErrors] = useState<FieldErrors<AnnouncementInput>>({});
  const [submitting, setSubmitting] = useState(false);

  if (!ready) return <PageLoader />;
  if (!user) return null;

  const set = <K extends keyof AnnouncementInput>(k: K, v: AnnouncementInput[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    const errs = validateAnnouncementForm(isAdmin ? form : { ...form, recruitmentId: null });
    setErrors(errs);
    if (Object.keys(errs).length > 0) {
      toast.error('请检查表单中的错误项');
      return;
    }
    setSubmitting(true);
    try {
      if (isAdmin) {
        const created = await repo.announcements.create(form);
        toast.success('公告已发布');
        navigate(`/announcements/${created.id}`, { replace: true });
      } else {
        const submission = await repo.announcements.submit({
          title: form.title,
          content: form.content,
          timeKind: form.timeKind,
          eventAt: form.eventAt,
          linkUrl: form.linkUrl,
        });
        toast.success('投稿已提交，等待管理员审核');
        navigate(`/me?tab=submissions&highlight=${submission.id}`, { replace: true });
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page-shell py-8 sm:py-10">
      <Link
        to="/"
        className="mb-4 inline-flex items-center gap-1 text-sm text-ink2 transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} /> 返回首页
      </Link>

      <h1 className="text-xl font-bold text-ink">{isAdmin ? '发布公告' : '投稿公告'}</h1>
      <p className="mt-1 text-sm text-ink2">
        {isAdmin ? '直接发布竞赛与活动公告。' : '投稿经管理员审核后发布。'}
      </p>

      <div className="mt-5">
        <InfoBanner>
          {isAdmin
            ? '公告发布后不可编辑，如需更正请删除后重新发布。'
            : '仅限竞赛/活动信息；需管理员审核，预计 24 小时内处理；每日最多 5 条，提交后不可改稿或撤回。'}
        </InfoBanner>
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

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
        </div>

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

        {isAdmin && (
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
        )}

        <div className="flex justify-end gap-3 border-t border-line pt-5">
          <Button variant="secondary" onClick={() => navigate(-1)}>
            取消
          </Button>
          <Button onClick={submit} loading={submitting}>
            {isAdmin ? '发布公告' : '提交审核'}
          </Button>
        </div>
      </div>
    </div>
  );
}
