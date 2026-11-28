import { ArrowLeft } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { clsx } from 'clsx';
import type { JobType, Tag } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { fromLocalInputValue, toLocalInputValue } from '@/domain/format';
import { JOB_TYPE_LABEL } from '@/domain/labels';
import { LIMITS, validateJobForm, type CreateJobInput, type FieldErrors } from '@/domain/validation';
import { Button } from '@/components/ui/Button';
import { Field, Input, Textarea } from '@/components/ui/Field';
import { NumberInput } from '@/components/ui/NumberInput';
import { ErrorState, InfoBanner, PageLoader } from '@/components/ui/Feedback';
import { toast } from '@/stores/toast';

const ALL_TYPES: JobType[] = ['competition', 'activity'];

const EMPTY: CreateJobInput = {
  type: 'competition',
  title: '',
  description: '',
  note: '',
  tags: [],
  minHeadcount: null,
  maxHeadcount: 5,
  deadline: '',
};

export function JobFormPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = !!id;
  const navigate = useNavigate();

  const { data: existing, loading, error } = useAsync(
    () => (id ? repo.jobs.detail(id) : Promise.resolve(null)),
    [id],
  );
  const tags = useAsync(() => repo.jobs.listTags(), []);

  const [form, setForm] = useState<CreateJobInput>(EMPTY);
  const [errors, setErrors] = useState<FieldErrors<CreateJobInput>>({});
  const [submitting, setSubmitting] = useState(false);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!existing || initialized) return;
    setForm({
      // 历史实验室实习记录对外展示为活动招聘，编辑时按活动类型提交
      type: existing.type === 'internship' ? 'activity' : existing.type,
      title: existing.title,
      description: existing.description,
      note: existing.note ?? '',
      tags: existing.tags,
      minHeadcount: existing.minHeadcount,
      maxHeadcount: existing.maxHeadcount,
      deadline: existing.deadline,
    });
    setInitialized(true);
  }, [existing, initialized]);

  if (loading) return <PageLoader />;
  if (isEdit && error) return <ErrorState message={error} />;
  if (isEdit && existing && !existing.permissions?.canEdit) {
    return <ErrorState message="仅发布者本人在进行中且未到截止时间时可编辑该招聘" />;
  }

  const set = <K extends keyof CreateJobInput>(k: K, v: CreateJobInput[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const toggleTag = (tag: Tag) => {
    setForm((f) => {
      const has = f.tags.some((t) => t.id === tag.id);
      return { ...f, tags: has ? f.tags.filter((t) => t.id !== tag.id) : [...f.tags, tag] };
    });
  };

  const submit = async () => {
    const errs = validateJobForm(form);
    if (isEdit && existing && form.maxHeadcount != null && form.maxHeadcount < existing.acceptedCount) {
      errs.maxHeadcount = `人数上限不能小于当前已接受人数（${existing.acceptedCount}）`;
    }
    setErrors(errs);
    if (Object.keys(errs).length > 0) {
      toast.error('请检查表单中的错误项');
      return;
    }
    setSubmitting(true);
    try {
      const job = isEdit ? await repo.jobs.update(id!, form) : await repo.jobs.create(form);
      toast.success(isEdit ? '招聘已更新，已通知相关申请人' : '招聘发布成功');
      navigate(`/jobs/${job.id}`, { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page-shell py-8 sm:py-10">
      <Link
        to={isEdit ? `/jobs/${id}` : '/jobs'}
        className="mb-4 inline-flex items-center gap-1 text-sm text-ink2 transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} /> {isEdit ? '返回招聘详情' : '返回招聘列表'}
      </Link>

      <h1 className="text-xl font-bold text-ink">{isEdit ? '编辑招聘' : '发布招聘'}</h1>
      <p className="mt-1 text-sm text-ink2">填写竞赛组队或校内活动的招聘信息。</p>

      <div className="mt-5">
        <InfoBanner>
          {isEdit
            ? '仅进行中且未到截止时间的招聘可修改，修改后会通知相关申请人。'
            : '截止时间须晚于当前时间且不超过一年，人数上限 1–200 人。'}
        </InfoBanner>
      </div>

      <div className="panel mt-5 flex flex-col gap-5 px-6 py-6">
        <Field label="招聘类型" required>
          <div className="flex flex-wrap gap-2">
            {ALL_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => set('type', t)}
                className={clsx(
                  'rounded-full px-4 py-2 text-sm transition-colors',
                  form.type === t
                    ? 'bg-primary-soft font-medium text-primary'
                    : 'border border-line text-ink2 hover:border-primary/40 hover:text-primary',
                )}
              >
                {JOB_TYPE_LABEL[t]}
              </button>
            ))}
          </div>
        </Field>

        <Field label="招聘名称" required error={errors.title} hint="1～100 字">
          <Input
            value={form.title}
            onChange={(e) => set('title', e.target.value)}
            placeholder="如：智能机器人创新竞赛组队"
            invalid={!!errors.title}
            maxLength={LIMITS.jobTitle}
          />
        </Field>

        <Field label="相关标签" required error={errors.tags} hint="可多选，用于招聘筛选">
          <div className="flex flex-wrap gap-2">
            {(tags.data ?? []).map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => toggleTag(t)}
                className={clsx(
                  'rounded-full px-3 py-1.5 text-sm transition-colors',
                  form.tags.some((x) => x.id === t.id)
                    ? 'bg-primary-soft font-medium text-primary'
                    : 'border border-line text-ink2 hover:border-primary/40 hover:text-primary',
                )}
              >
                {t.name}
              </button>
            ))}
            {tags.loading && <span className="text-xs text-muted">加载标签中…</span>}
            {!tags.loading && (tags.data ?? []).length === 0 && (
              <span className="text-xs text-muted">暂无可用标签，请联系管理员。</span>
            )}
          </div>
        </Field>

        <Field
          label="需求描述"
          required
          error={errors.description}
          hint={`1～${LIMITS.jobDescription} 字，纯文本`}
        >
          <Textarea
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="请描述招聘需求、目标、期望投入与联系方式等信息"
            invalid={!!errors.description}
            className="min-h-[160px]"
            maxLength={LIMITS.jobDescription}
          />
          <div className="text-right text-xs text-muted">
            {form.description.length}/{LIMITS.jobDescription}
          </div>
        </Field>

        <Field
          label="补充说明（选填）"
          error={errors.note}
          hint={`最多 ${LIMITS.note} 字，展示在招聘详情`}
        >
          <Textarea
            value={form.note}
            onChange={(e) => set('note', e.target.value)}
            placeholder="如：面试安排、组队偏好、联系方式等补充信息"
            invalid={!!errors.note}
            className="min-h-[100px]"
            maxLength={LIMITS.note}
          />
          <div className="text-right text-xs text-muted">
            {form.note.length}/{LIMITS.note}
          </div>
        </Field>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="人数上限" required error={errors.maxHeadcount} hint={`1–${LIMITS.headcount} 人`}>
            <NumberInput
              min={1}
              max={LIMITS.headcount}
              value={form.maxHeadcount}
              onChange={(v) => set('maxHeadcount', v)}
              invalid={!!errors.maxHeadcount}
              aria-label="人数上限"
            />
          </Field>
          <Field label="人数下限（选填）" error={errors.minHeadcount} hint="仅用于展示预期">
            <NumberInput
              min={1}
              max={LIMITS.headcount}
              value={form.minHeadcount}
              onChange={(v) => set('minHeadcount', v)}
              placeholder="可留空"
              invalid={!!errors.minHeadcount}
              aria-label="人数下限"
            />
          </Field>
          <Field label="截止时间" required error={errors.deadline}>
            <Input
              type="datetime-local"
              value={form.deadline ? toLocalInputValue(form.deadline) : ''}
              onChange={(e) => set('deadline', fromLocalInputValue(e.target.value))}
              invalid={!!errors.deadline}
            />
          </Field>
        </div>

        <div className="flex justify-end gap-3 border-t border-line pt-5">
          <Button variant="secondary" onClick={() => navigate(-1)}>
            取消
          </Button>
          <Button onClick={submit} loading={submitting}>
            {isEdit ? '保存修改' : '发布招聘'}
          </Button>
        </div>
      </div>
    </div>
  );
}
