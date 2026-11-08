import { ArrowLeft, Check, FileText, Minus, X } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { Application } from '@/domain/models';
import { repo } from '@/data';
import { fetchAllPages } from '@/data/fetchAll';
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
  const apps = useAsync(
    () => fetchAllPages((p, s) => repo.applications.listForJob(id!, { page: p, pageSize: s })),
    [id],
  );
  const [preview, setPreview] = useState<Application | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  if (job.loading || apps.loading) return <PageLoader />;
  if (job.error) return <ErrorState message={job.error} />;
  if (apps.error) return <ErrorState message={apps.error} />;
  if (!job.data) return null;

  const full = job.data.acceptedCount >= job.data.maxHeadcount;

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

  const openPreview = async (app: Application) => {
    setPreviewLoading(true);
    try {
      const detail = await repo.applications.detail(app.id);
      setPreview(detail);
      // 发布者查看后确认「已修改」已阅（用刚读到的 updated_at 做版本比较）
      if (detail.modified) {
        await repo.applications.clearModified(detail.id, detail.updatedAt);
        apps.reload();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '加载简历失败');
    } finally {
      setPreviewLoading(false);
    }
  };

  const download = async () => {
    if (!preview) return;
    try {
      await repo.applications.downloadResume(preview.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '下载失败');
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
          「{job.data.title}」· 已接受 {job.data.acceptedCount} / 计划 {job.data.maxHeadcount}
        </span>
      </div>

      <InfoBanner>
        接受、拒绝为终态；暂留仅为发布者私有标记，不通知申请人；状态变更后自动向申请者推送站内通知。
      </InfoBanner>

      <div className="mt-5 flex flex-col gap-3">
        {apps.data && apps.data.length === 0 ? (
          <EmptyState title="暂无收到的申请" />
        ) : (
          apps.data?.map((app) => (
            <ApplicationRow
              key={app.id}
              app={app}
              full={full}
              busy={busyId === app.id}
              onMark={(a) => mark(app, a)}
              onPreview={() => openPreview(app)}
            />
          ))
        )}
      </div>

      <Modal open={!!preview || previewLoading} title="简历详情" onClose={() => setPreview(null)}>
        {previewLoading && !preview ? (
          <p className="py-6 text-center text-sm text-muted">加载中…</p>
        ) : preview ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-ink">
                {preview.applicant.name} · {ROLE_LABEL[preview.applicant.role]}
              </span>
              <ApplicationStatusBadge status={preview.status} />
            </div>
            {preview.resume === null ? (
              <p className="rounded-md bg-muted-soft px-4 py-3 text-sm text-muted">
                该申请已撤回或失效，简历文件与补充说明不再展示。
              </p>
            ) : (
              <>
                <div className="flex items-center gap-3 rounded-md border border-line px-4 py-3">
                  <FileText className="h-6 w-6 text-primary" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-ink">{preview.resume.fileName}</p>
                    <p className="text-xs text-ink2">{fileSizeLabel(preview.resume.size)}</p>
                  </div>
                  <Button size="sm" variant="secondary" onClick={download} disabled={!preview.canDownloadResume}>
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
        ) : null}
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
  const processing = app.status === 'processing';
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-ink">{app.applicant.name}</span>
          <span className="rounded-full bg-muted-soft px-2 py-0.5 text-xs text-ink2">
            {ROLE_LABEL[app.applicant.role]}
          </span>
          <ApplicationStatusBadge status={app.status} />
          {processing && app.publisherMark === 'hold' && (
            <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning">暂留</span>
          )}
          {app.modified && processing && (
            <span className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning">
              <span className="h-1.5 w-1.5 rounded-full bg-warning" /> 已修改
            </span>
          )}
        </div>
        <p className="text-xs text-ink2">提交于 {formatDateTime(app.createdAt)}</p>
      </div>

      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" onClick={onPreview}>
          查看简历
        </Button>
        {processing && (
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
