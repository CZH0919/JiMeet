import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { JobType } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { FIELDS } from '@/domain/labels';
import { validateJobForm, type CreateJobInput, type FieldErrors } from '@/domain/validation';
import { Button } from '@/components/ui/Button';
import { Field, Input, Select, Textarea } from '@/components/ui/Field';
import { ErrorState, InfoBanner, PageLoader } from '@/components/ui/Feedback';
import { toast } from '@/stores/toast';

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function JobFormPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = !!id;
  const { user } = useAuth();
  const navigate = useNavigate();

  const lockedType: JobType = user?.role === 'teacher' ? 'campus_activity' : 'competition';

  const { data: existing, loading, error } = useAsync(
    () => (id ? repo.jobs.detail(id) : Promise.resolve(null)),
    [id],
  );

  const [form, setForm] = useState<CreateJobInput>({
    type: lockedType,
    title: '',
    description: '',
    requirement: '',
    field: '',
    recruitCount: 1,
    deadline: '',
  });
  const [errors, setErrors] = useState<FieldErrors<CreateJobInput>>({});
  const [submitting, setSubmitting] = useState(false);
  const [initialized, setInitialized] = useState(false);

  // 编辑模式：回填数据
  useEffect(() => {
    if (existing && !initialized) {
      setForm({
        type: existing.type,
        title: existing.title,
        description: existing.description,
        requirement: existing.requirement,
        field: existing.field,
        recruitCount: existing.recruitCount,
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

  const submit = async () => {
    const errs = validateJobForm(form);
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
        {user?.role === 'student' ? '学生可发布竞赛组队类招聘' : '教师可发布校内活动类招聘'}
      </p>

      <InfoBanner>
        {isEdit
          ? '仅进行中招聘可修改；修改后会通知所有申请人。'
          : '发布后进入招聘列表，按发布时间倒序排列。'}
      </InfoBanner>

      <div className="mt-6 flex flex-col gap-5 rounded-xl border border-line bg-surface p-6">
        <Field label="招聘类型" required>
          <div className="flex gap-2">
            {(
              [
                { key: 'competition', label: '竞赛组队' },
                { key: 'campus_activity', label: '活动招聘' },
              ] as { key: JobType; label: string }[]
            ).map((t) => (
              <button
                key={t.key}
                type="button"
                disabled={t.key !== lockedType}
                onClick={() => set('type', t.key)}
                className={
                  form.type === t.key
                    ? 'rounded-md bg-primary-soft px-4 py-2 text-sm font-medium text-primary'
                    : 'rounded-md border border-line px-4 py-2 text-sm text-muted'
                }
              >
                {t.label}
                {t.key !== lockedType && '（身份不符）'}
              </button>
            ))}
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

        <Field label="相关领域" required error={errors.field}>
          <Select value={form.field} onChange={(e) => set('field', e.target.value)} invalid={!!errors.field}>
            <option value="">请选择领域</option>
            {FIELDS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </Select>
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

        <Field label="用人要求 / 补充说明" error={errors.requirement}>
          <Textarea
            value={form.requirement}
            onChange={(e) => set('requirement', e.target.value)}
            placeholder="选填，补充说明用人要求"
            invalid={!!errors.requirement}
            maxLength={1000}
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="计划招募人数" required error={errors.recruitCount}>
            <Input
              type="number"
              min={1}
              max={50}
              value={form.recruitCount}
              onChange={(e) => set('recruitCount', Number(e.target.value))}
              invalid={!!errors.recruitCount}
            />
          </Field>
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
