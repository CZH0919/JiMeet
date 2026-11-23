import { ArrowLeft, Check, FileText, Minus, RotateCcw, X } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { clsx } from 'clsx';
import type { Application, ApplicationStatus } from '@/domain/models';
import { repo } from '@/data';
import { fetchAllPages } from '@/data/fetchAll';
import { useAsync } from '@/features/useAsync';
import { formatDateTime, formatRelative } from '@/domain/format';
import { APPLICATION_STATUS_LABEL, ROLE_LABEL } from '@/domain/labels';
import { ApplicationStatusBadge } from '@/components/ui/StatusBadge';
import { Button } from '@/components/ui/Button';
import { EmptyState, ErrorState, InfoBanner, PageLoader } from '@/components/ui/Feedback';
import { Modal } from '@/components/ui/Modal';
import { ResumePreview } from '@/components/application/ResumePreview';
import { toast } from '@/stores/toast';

const STATUS_TABS: { key: ApplicationStatus | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'processing', label: APPLICATION_STATUS_LABEL.processing },
  { key: 'accepted', label: APPLICATION_STATUS_LABEL.accepted },
  { key: 'rejected', label: APPLICATION_STATUS_LABEL.rejected },
  { key: 'withdrawn', label: APPLICATION_STATUS_LABEL.withdrawn },
  { key: 'invalid', label: APPLICATION_STATUS_LABEL.invalid },
];

type Action = 'accept' | 'hold' | 'unhold' | 'reject';

export function JobApplicationsPage() {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState<ApplicationStatus | 'all'>('processing');
  const job = useAsync(() => repo.jobs.detail(id!), [id]);
  const apps = useAsync(
    () =>
      fetchAllPages((p, s) =>
        repo.applications.listForJob(id!, {
          page: p,
          pageSize: s,
          status: status === 'all' ? undefined : status,
        }),
      ),
    [id, status],
  );

  const [detail, setDetail] = useState<Application | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<Action | null>(null);

  if (job.loading || apps.loading) return <PageLoader />;
  if (job.error) return <ErrorState message={job.error} onRetry={job.reload} />;
  if (apps.error) return <ErrorState message={apps.error} onRetry={apps.reload} />;
  if (!job.data) return null;

  const jobData = job.data;
  const full = jobData.acceptedCount >= jobData.maxHeadcount;

  const refresh = async () => {
    await Promise.all([job.reload(), apps.reload()]);
  };

  const openDetail = async (app: Application) => {
    setDetailLoading(true);
    try {
      const loaded = await repo.applications.detail(app.id);
      setDetail(loaded);
      // 发布者查看后确认「已修改」已阅（用刚读到的 updated_at 做版本比较）
      if (loaded.modified) {
        await repo.applications.clearModified(loaded.id, loaded.updatedAt);
        void apps.reload();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '加载申请详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const mark = async (action: Action) => {
    if (!detail) return;
    setBusyAction(action);
    try {
      const updated = await repo.applications.mark(detail.id, action);
      if (action === 'accept') {
        toast.success('已确认该申请，申请人将收到站内通知');
        setDetail(null);
      } else if (action === 'reject') {
        toast.success('已拒绝该申请，申请人将收到站内通知');
        setDetail(null);
      } else if (action === 'hold') {
        toast.success('已暂留（状态仍为处理中，申请人不可见）');
        setDetail({ ...detail, publisherMark: 'hold', ...preserveDetail(updated) });
      } else {
        toast.success('已取消暂留');
        setDetail({ ...detail, publisherMark: 'none', ...preserveDetail(updated) });
      }
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作失败');
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="page-shell max-w-[1000px] py-8 sm:py-10">
      <Link
        to={`/jobs/${id}`}
        className="mb-4 inline-flex items-center gap-1 text-sm text-ink2 transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} /> 返回招聘详情
      </Link>

      <div className="flex flex-col gap-3">
        <h1 className="text-xl font-bold text-ink">招聘申请管理</h1>
        <p className="text-sm text-ink2">
          「{jobData.title}」· 已接受 {jobData.acceptedCount} / {jobData.maxHeadcount}
        </p>
      </div>

      <div className="mt-4">
        <InfoBanner>
          查看简历后可直接处理；确认与拒绝不可撤销，并会通知申请人；暂留仅发布者可见。
          {full && ' 当前已满员，无法再确认新的申请。'}
        </InfoBanner>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-1 border-b border-line pb-2">
        {STATUS_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setStatus(t.key)}
            className={clsx(
              'rounded-full px-3.5 py-1.5 text-sm transition-colors',
              status === t.key
                ? 'bg-primary-soft font-medium text-primary'
                : 'text-ink2 hover:bg-muted-soft hover:text-ink',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-4 flex flex-col gap-3">
        {apps.data && apps.data.length === 0 ? (
          <EmptyState title="该分类下暂无申请" />
        ) : (
          apps.data?.map((app) => (
            <ApplicationRow key={app.id} app={app} onOpen={() => void openDetail(app)} />
          ))
        )}
      </div>

      <Modal
        open={!!detail || detailLoading}
        title="申请详情"
        description={detail ? `${detail.applicant.name} · ${ROLE_LABEL[detail.applicant.role]}` : undefined}
        onClose={() => setDetail(null)}
        width="max-w-3xl"
        bodyClassName="max-h-[76vh] overflow-y-auto px-6 py-5"
        footer={
          detail ? (
            <>
              <Button variant="secondary" onClick={() => setDetail(null)} disabled={!!busyAction}>
                关闭
              </Button>
              {detail.status === 'processing' && detail.canProcess && (
                <>
                  <Button
                    variant="secondary"
                    disabled={!!busyAction}
                    loading={busyAction === 'hold' || busyAction === 'unhold'}
                    onClick={() => void mark(detail.publisherMark === 'hold' ? 'unhold' : 'hold')}
                  >
                    {detail.publisherMark === 'hold' ? <RotateCcw size={14} /> : <Minus size={14} />}
                    {detail.publisherMark === 'hold' ? '取消暂留' : '暂留'}
                  </Button>
                  <Button
                    variant="danger-outline"
                    disabled={!!busyAction}
                    loading={busyAction === 'reject'}
                    onClick={() => void mark('reject')}
                  >
                    <X size={14} /> 拒绝
                  </Button>
                  <Button
                    variant="primary"
                    disabled={!!busyAction || full}
                    loading={busyAction === 'accept'}
                    title={full ? '已满员，无法确认' : '确认该申请'}
                    onClick={() => void mark('accept')}
                  >
                    <Check size={14} /> 确认
                  </Button>
                </>
              )}
            </>
          ) : null
        }
      >
        {detailLoading && !detail ? (
          <p className="py-10 text-center text-sm text-muted">加载中…</p>
        ) : detail ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <ApplicationStatusBadge status={detail.status} />
              {detail.status === 'processing' && detail.publisherMark === 'hold' && (
                <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning">暂留</span>
              )}
              {detail.modified && detail.status === 'processing' && (
                <span className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning">
                  <span className="h-1.5 w-1.5 rounded-full bg-warning" /> 已修改
                </span>
              )}
              <span className="text-xs text-ink2">
                提交于 {formatDateTime(detail.createdAt)} · 更新于 {formatDateTime(detail.updatedAt)}
              </span>
            </div>

            {detail.resume === null ? (
              <p className="rounded-md bg-muted-soft px-4 py-3 text-sm text-muted">
                该申请已撤回、已失效或招聘已删除，简历文件与补充说明不再展示。
              </p>
            ) : (
              <>
                <ResumePreview
                  applicationId={detail.id}
                  file={detail.resume}
                  canDownload={detail.canDownloadResume}
                />

                {detail.note ? (
                  <div>
                    <p className="mb-1 text-xs font-medium text-ink2">补充说明</p>
                    <p className="whitespace-pre-wrap rounded-md bg-page px-4 py-3 text-sm leading-relaxed text-ink2">
                      {detail.note}
                    </p>
                  </div>
                ) : (
                  <p className="text-xs text-muted">申请人未填写补充说明。</p>
                )}
              </>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}

/** 处理动作返回的新对象只用于刷新状态字段，简历与说明仍以详情接口为准 */
function preserveDetail(updated: Application): Partial<Application> {
  return {
    status: updated.status,
    decidedAt: updated.decidedAt,
    updatedAt: updated.updatedAt,
    canProcess: updated.canProcess,
    modified: false,
  };
}

function ApplicationRow({ app, onOpen }: { app: Application; onOpen: () => void }) {
  const processing = app.status === 'processing' && app.canProcess;
  const held = app.publisherMark === 'hold';

  return (
    <div className="panel flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-ink">{app.applicant.name}</span>
          <span className="rounded-full bg-muted-soft px-2 py-0.5 text-xs text-ink2">
            {ROLE_LABEL[app.applicant.role]}
          </span>
          <ApplicationStatusBadge status={app.status} />
          {processing && held && (
            <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning">暂留</span>
          )}
          {app.modified && processing && (
            <span className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning">
              <span className="h-1.5 w-1.5 rounded-full bg-warning" /> 已修改
            </span>
          )}
        </div>
        <p className="text-xs text-ink2">
          提交于 {formatDateTime(app.createdAt)}（{formatRelative(app.createdAt)}）
          {app.resume && ` · ${app.resume.fileName}`}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" onClick={onOpen}>
          <FileText size={14} /> 查看简历
        </Button>
      </div>
    </div>
  );
}
