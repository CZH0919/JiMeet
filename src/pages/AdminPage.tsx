import { ScrollText, ShieldAlert, Trash2 } from 'lucide-react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { clsx } from 'clsx';
import type { Job } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { ROLE_LABEL } from '@/domain/labels';
import { formatDateTime } from '@/domain/jobStatus';
import { JobStatusBadge } from '@/components/ui/StatusBadge';
import { FieldTag, JobTypeTag } from '@/components/job/JobTypeTag';
import { Button } from '@/components/ui/Button';
import { Field, Textarea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';
import { validateModerationReason } from '@/domain/validation';
import { toast } from '@/stores/toast';

export function AdminPage() {
  const [tab, setTab] = useState<'jobs' | 'logs'>('jobs');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const jobs = useAsync(() => repo.admin.listAllJobs({ type: 'all', page, pageSize }), [page]);
  const logs = useAsync(() => repo.admin.listAuditLogs({ page: 1, pageSize: 100 }), [tab]);

  const [target, setTarget] = useState<Job | null>(null);
  const [reason, setReason] = useState('');
  const [reasonErr, setReasonErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const doRemove = async () => {
    if (!target) return;
    const err = validateModerationReason(reason);
    setReasonErr(err);
    if (err) return;
    setBusy(true);
    try {
      await repo.admin.removeJobWithReason(target.id, reason);
      toast.success('已删除，并通知发布者、写入审计日志');
      setTarget(null);
      setReason('');
      jobs.reload();
      logs.reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="flex items-center gap-2 text-xl font-semibold text-ink">
        <ShieldAlert size={20} className="text-danger" /> 管理员后台
      </h1>
      <p className="mt-1 text-sm text-ink2">内容治理 · 全平台招聘查看与不合规内容处置</p>

      <div className="mt-5 flex gap-1 border-b border-line">
        <TabBtn active={tab === 'jobs'} onClick={() => setTab('jobs')} icon={<ShieldAlert size={15} />} label="招聘帖子管理" />
        <TabBtn active={tab === 'logs'} onClick={() => setTab('logs')} icon={<ScrollText size={15} />} label="审计日志" />
      </div>

      {tab === 'jobs' ? (
        <div className="mt-5">
          {jobs.loading ? (
            <PageLoader />
          ) : jobs.error ? (
            <ErrorState message={jobs.error} onRetry={jobs.reload} />
          ) : jobs.data && jobs.data.items.length === 0 ? (
            <EmptyState title="暂无招聘" />
          ) : (
            <>
              <div className="flex flex-col gap-3">
                {jobs.data?.items.map((job) => (
                  <div key={job.id} className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 sm:flex-row sm:items-center">
                    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link to={`/jobs/${job.id}`} className="text-sm font-semibold text-ink hover:text-primary">
                          {job.title}
                        </Link>
                        <JobStatusBadge status={job.status} />
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <JobTypeTag type={job.type} />
                        <FieldTag field={job.field} />
                        <span className="text-xs text-ink2">
                          发布者 {job.publisher.name}（{ROLE_LABEL[job.publisher.role]}）
                        </span>
                      </div>
                    </div>
                    <Button size="sm" variant="danger" onClick={() => setTarget(job)}>
                      <Trash2 size={14} /> 删除
                    </Button>
                  </div>
                ))}
              </div>
              <Pagination page={page} pageSize={pageSize} total={jobs.data?.total ?? 0} onChange={setPage} />
            </>
          )}
        </div>
      ) : (
        <div className="mt-5">
          {logs.loading ? (
            <PageLoader />
          ) : logs.error ? (
            <ErrorState message={logs.error} />
          ) : logs.data && logs.data.items.length === 0 ? (
            <EmptyState title="暂无审计日志" />
          ) : (
            <div className="flex flex-col gap-3">
              {logs.data?.items.map((log) => (
                <div key={log.id} className="rounded-lg border border-line bg-surface p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-ink">
                      {log.operatorName}（{ROLE_LABEL[log.operatorRole]}）· 删除招聘
                    </span>
                    <span className="text-xs text-muted">{formatDateTime(log.createdAt)}</span>
                  </div>
                  <p className="mt-1 text-sm text-ink2">对象：「{log.targetTitle}」</p>
                  <p className="mt-1 text-sm text-ink2">原因：{log.reason}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <Modal
        open={!!target}
        title="删除不合规内容"
        onClose={() => setTarget(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setTarget(null)}>
              取消
            </Button>
            <Button variant="danger" onClick={doRemove} loading={busy}>
              确认删除
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink2">
            你正在删除「{target?.title}」。该操作会通知发布者并记入审计日志，请填写删除原因（至少 10 字）。
          </p>
          <Field error={reasonErr ?? undefined}>
            <Textarea
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                setReasonErr(null);
              }}
              placeholder="请填写删除原因（至少 10 字）"
            />
          </Field>
        </div>
      </Modal>
    </div>
  );
}

function TabBtn({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: ReactNode; label: string }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
        active ? 'border-danger text-danger' : 'border-transparent text-ink2 hover:text-ink',
      )}
    >
      {icon} {label}
    </button>
  );
}
