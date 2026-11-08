import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { JobType, Tag } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { JOB_TYPE_LABEL } from '@/domain/labels';
import { validateJobForm, type CreateJobInput, type FieldErrors } from '@/domain/validation';
import { Button } from '@/components/ui/Button';
import { Field, Input, Textarea } from '@/components/ui/Field';
import { ErrorState, InfoBanner, PageLoader } from '@/components/ui/Feedback';
import { toast } from '@/stores/toast';
import { clsx } from 'clsx';

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

const ALL_TYPES: JobType[] = ['competition', 'activity', 'internship', 'competition_notice'];

export function JobFormPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = !!id;
  const { user } = useAuth();
  const navigate = useNavigate();

  const allowedTypes: JobType[] =
    user?.role === 'teacher' ? ['activity', 'internship', 'competition_notice'] : ['competition'];
  const defaultType = allowedTypes[0];

  const { data: existing, loading, error } = useAsync(
    () => (id ? repo.jobs.detail(id) : Promise.resolve(null)),
    [id],
  );
  const tags = useAsync(() => repo.jobs.listTags(), []);

  const [form, setForm] = useState<CreateJobInput>({
    type: defaultType,
    title: '',
    description: '',
    tags: [],
    minHeadcount: null,
    maxHeadcount: 1,
    deadline: '',
  });
  const [errors, setErrors] = useState<FieldErrors<CreateJobInput>>({});
  const [submitting, setSubmitting] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const isNotice = form.type === 'competition_notice';

  // 编辑模式：回填数据
  useEffect(() => {
    if (existing && !initialized) {
      setForm({
        type: existing.type,
        title: existing.title,
        description: existing.description,
        tags: existing.tags,
        minHeadcount: existing.minHeadcount,
        maxHeadcount: existing.maxHeadcount,
        deadline: existing.deadline,
      });
      setInitialized(true);
    }
  }, [existing, initialized]);

  if (loading) return <PageLoader />;
  if (isEdit && error) return <ErrorState message={error} />;
  if (isEdit && existing && existing.publisher.id !== user?.id) {
    return <ErrorState message="仅可编辑本人发布的招聘" />;
  }

  const set = <K extends keyof CreateJobInput>(k: K, v: CreateJobInput[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const toggleTag = (tag: Tag) => {
    setForm((f) => {
      const has = f.tags.some((t) => t.id === tag.id);
      return {
        ...f,
        tags: has ? f.tags.filter((t) => t.id !== tag.id) : [...f.tags, tag],
      };
    });
  };

  const submit = async () => {
    const errs = validateJobForm(form);
    if (isEdit && existing && !isNotice && form.maxHeadcount < existing.acceptedCount) {
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
      toast.success(isEdit ? '招聘已更新' : '招聘发布成功');
      navigate(`/jobs/${job.id}`, { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-1 text-xl font-semibold text-ink">{isEdit ? '编辑招聘' : '发布招聘'}</h1>
      <p className="mb-6 text-sm text-ink2">
        {user?.role === 'student' ? '学生可发布竞赛组队类招聘' : '教师可发布活动招聘、实验室实习或竞赛通知'}
      </p>

      <InfoBanner>
        {isEdit
          ? '仅进行中招聘可修改；修改后会通知所有未拒绝申请人。'
          : '发布后进入招聘列表，按发布时间倒序排列。'}
      </InfoBanner>

      <div className="mt-6 flex flex-col gap-5 rounded-xl border border-line bg-surface p-6">
        <Field label="招聘类型" required>
          <div className="flex flex-wrap gap-2">
            {ALL_TYPES.map((t) => {
              const allowed = allowedTypes.includes(t);
              return (
                <button
                  key={t}
                  type="button"
                  disabled={!allowed}
                  onClick={() => set('type', t)}
                  className={
                    form.type === t
                      ? 'rounded-md bg-primary-soft px-4 py-2 text-sm font-medium text-primary'
                      : allowed
                        ? 'rounded-md border border-line px-4 py-2 text-sm text-ink2 hover:border-primary'
                        : 'rounded-md border border-line px-4 py-2 text-sm text-muted'
                  }
                >
                  {JOB_TYPE_LABEL[t]}
                  {!allowed && '（身份不符）'}
                </button>
              );
            })}
          </div>
        </Field>

        <Field label="名称" required error={errors.title}>
          <Input
            value={form.title}
            onChange={(e) => set('title', e.target.value)}
            placeholder="如：智能机器人创新竞赛组队"
            invalid={!!errors.title}
            maxLength={60}
          />
        </Field>

        <Field label="相关标签" required error={errors.tags}>
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
                    : 'border border-line text-ink2 hover:border-primary',
                )}
              >
                {t.name}
              </button>
            ))}
            {tags.loading && <span className="text-xs text-muted">加载标签中…</span>}
          </div>
        </Field>

        <Field label="需求描述" required error={errors.description}>
          <Textarea
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="请描述招聘需求、目标与期望投入"
            invalid={!!errors.description}
            maxLength={2000}
          />
        </Field>

        <div className={isNotice ? 'grid grid-cols-1 gap-4' : 'grid grid-cols-2 gap-4'}>
          {!isNotice && (
            <>
              <Field label="计划招募人数（上限）" required error={errors.maxHeadcount}>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={form.maxHeadcount}
                  onChange={(e) => set('maxHeadcount', Number(e.target.value))}
                  invalid={!!errors.maxHeadcount}
                />
              </Field>
              <Field label="人数下限（选填，仅展示预期）" error={errors.minHeadcount}>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={form.minHeadcount ?? ''}
                  onChange={(e) =>
                    set('minHeadcount', e.target.value === '' ? null : Number(e.target.value))
                  }
                  placeholder="可留空"
                  invalid={!!errors.minHeadcount}
                />
              </Field>
            </>
          )}
          <Field label="截止时间" required error={errors.deadline}>
            <Input
              type="datetime-local"
              value={form.deadline ? toLocalInput(form.deadline) : ''}
              onChange={(e) =>
                set('deadline', e.target.value ? new Date(e.target.value).toISOString() : '')
              }
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
