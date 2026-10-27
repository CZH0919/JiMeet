import { ArrowLeft, Check, FileText, Minus, X } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { Application } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { ROLE_LABEL } from '@/domain/labels';
import { formatDateTime } from '@/domain/jobStatus';
import { ApplicationStatusBadge } from '@/components/ui/StatusBadge';
import { Button } from '@/components/ui/Button';
import { EmptyState, ErrorState, InfoBanner, PageLoader } from '@/components/ui/Feedback';
import { Modal } from '@/components/ui/Modal';
import { fileSizeLabel } from '@/domain/validation';
import { toast } from '@/stores/toast';

export function JobApplicationsPage() {
  const { id } = useParams<{ id: string }>();
  const job = useAsync(() => repo.jobs.detail(id!), [id]);
  const apps = useAsync(() => repo.applications.listForJob(id!, { page: 1, pageSize: 100 }), [id]);
  const [preview, setPreview] = useState<Application | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  if (job.loading || apps.loading) return <PageLoader />;
  if (job.error) return <ErrorState message={job.error} />;
  if (apps.error) return <ErrorState message={apps.error} />;
  if (!job.data) return null;

  const full = job.data.acceptedCount >= job.data.recruitCount;

  const mark = async (app: Application, action: 'accept' | 'hold' | 'reject') => {
    setBusyId(app.id);
    try {
      await repo.applications.mark(app.id, action);
      if (action === 'accept') toast.success('已确认该申请');
      if (action === 'reject') toast.success('已拒绝该申请');
      if (action === 'hold') toast.success('已暂留（状态仍为处理中）');
      await Promise.all([job.reload(), apps.reload()]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作失败');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link to={`/jobs/${id}`} className="mb-4 inline-flex items-center gap-1 text-sm text-ink2 hover:text-ink">
        <ArrowLeft size={15} /> 返回招聘详情
      </Link>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink">招聘申请管理</h1>
        <span className="text-sm text-ink2">
          「{job.data.title}」· 已接受 {job.data.acceptedCount} / 计划 {job.data.recruitCount}
        </span>
      </div>

      <InfoBanner>
        接受、拒绝为终态；暂留仅为发布者私有标记，不通知申请人；状态变更后自动向申请者推送站内通知。
      </InfoBanner>

      <div className="mt-5 flex flex-col gap-3">
        {apps.data && apps.data.items.length === 0 ? (
          <EmptyState title="暂无收到的申请" />
        ) : (
          apps.data?.items.map((app) => (
            <ApplicationRow
              key={app.id}
              app={app}
              full={full}
              busy={busyId === app.id}
              onMark={(a) => mark(app, a)}
              onPreview={() => setPreview(app)}
            />
          ))
        )}
      </div>

      <Modal open={!!preview} title="简历详情" onClose={() => setPreview(null)}>
        {preview && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-ink">
                {preview.applicant.name} · {ROLE_LABEL[preview.applicant.role]}
              </span>
              <ApplicationStatusBadge status={preview.status} />
            </div>
            {preview.resumeHidden ? (
              <p className="rounded-md bg-muted-soft px-4 py-3 text-sm text-muted">
                该申请已撤回，简历文件与补充说明不再对发布者展示。
              </p>
            ) : (
              <>
                <div className="flex items-center gap-3 rounded-md border border-line px-4 py-3">
                  <FileText className="h-6 w-6 text-primary" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-ink">{preview.resume.fileName}</p>
                    <p className="text-xs text-ink2">{fileSizeLabel(preview.resume.size)}</p>
                  </div>
                  <Button size="sm" variant="secondary" onClick={() => toast.info('演示环境暂不提供真实下载')}>
                    下载
                  </Button>
                </div>
                {preview.note && (
                  <div>
                    <p className="mb-1 text-xs font-medium text-ink2">补充说明</p>
                    <p className="rounded-md bg-page px-4 py-3 text-sm leading-relaxed text-ink2">{preview.note}</p>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

function ApplicationRow({
  app,
  full,
  busy,
  onMark,
  onPreview,
}: {
  app: Application;
  full: boolean;
  busy: boolean;
  onMark: (a: 'accept' | 'hold' | 'reject') => void;
  onPreview: () => void;
}) {
  const pending = app.status === 'pending';
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-ink">{app.applicant.name}</span>
          <span className="rounded-full bg-muted-soft px-2 py-0.5 text-xs text-ink2">
            {ROLE_LABEL[app.applicant.role]}
          </span>
          <ApplicationStatusBadge status={app.status} />
        </div>
        <p className="text-xs text-ink2">
          {app.applicant.role === 'student' ? '学号' : '工号'} {app.applicant.id} · 提交于{' '}
          {formatDateTime(app.createdAt)}
        </p>
        {app.note && !app.resumeHidden && (
          <p className="line-clamp-1 text-sm text-ink2">{app.note}</p>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" onClick={onPreview}>
          {app.resumeHidden ? '已撤回' : '查看简历'}
        </Button>
        {pending && (
          <>
            <Button
              size="sm"
              variant="primary"
              disabled={full || busy}
              title={full ? '已满员，无法确认' : '确认'}
              onClick={() => onMark('accept')}
            >
              <Check size={14} /> 确认
            </Button>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => onMark('hold')}>
              <Minus size={14} /> 暂留
            </Button>
            <Button size="sm" variant="danger-outline" disabled={busy} onClick={() => onMark('reject')}>
              <X size={14} /> 拒绝
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
