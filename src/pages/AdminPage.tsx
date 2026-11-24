import { FileText, Search, ShieldAlert, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { clsx } from 'clsx';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { formatDateTime } from '@/domain/format';
import { ROLE_LABEL, TIME_KIND_LABEL } from '@/domain/labels';
import { validateModerationReason } from '@/domain/validation';
import { JobStatusBadge } from '@/components/ui/StatusBadge';
import { JobTypeTag, TagTag } from '@/components/job/JobTypeTag';
import { Button } from '@/components/ui/Button';
import { Field, Textarea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';
import { toast } from '@/stores/toast';

type Tab = 'jobs' | 'announcements';

interface Target {
  kind: Tab;
  id: string;
  title: string;
}

const PAGE_SIZE = 20;

export function AdminPage() {
  const [tab, setTab] = useState<Tab>('jobs');

  return (
    <div className="page-shell max-w-[1000px] py-8 sm:py-10">
      <h1 className="flex items-center gap-2 text-xl font-bold text-ink">
        <ShieldAlert size={20} className="text-danger" /> 内容治理后台
      </h1>
      <p className="mt-1 text-sm text-ink2">
        删除不合规内容需填写原因并记入审计日志；不获得申请或简历的读取权限。
      </p>

      <div className="mt-6 flex gap-1 border-b border-line">
        {(
          [
            { key: 'jobs', label: '招聘治理' },
            { key: 'announcements', label: '公告治理' },
          ] as { key: Tab; label: string }[]
        ).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              '-mb-px border-b-2 px-4 py-2.5 text-sm transition-colors',
              tab === t.key
                ? 'border-danger font-medium text-danger'
                : 'border-transparent text-ink2 hover:text-ink',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-5">{tab === 'jobs' ? <JobsGovernPanel /> : <AnnouncementsGovernPanel />}</div>
    </div>
  );
}

function JobsGovernPanel() {
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [target, setTarget] = useState<Target | null>(null);

  const jobs = useAsync(
    () => repo.jobs.list({ type: 'all', keyword, page, pageSize: PAGE_SIZE }),
    [page, keyword],
  );

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:w-72">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
            placeholder="搜索招聘标题或描述"
            className="w-full rounded-full border border-line bg-surface py-2 pl-10 pr-4 text-sm focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/10"
          />
        </div>
        <p className="text-sm text-ink2">{jobs.data ? `共 ${jobs.data.total} 条` : '加载中…'}</p>
      </div>

      <div className="mt-4">
        {jobs.loading ? (
          <PageLoader />
        ) : jobs.error ? (
          <ErrorState message={jobs.error} onRetry={jobs.reload} />
        ) : !jobs.data || jobs.data.items.length === 0 ? (
          <EmptyState title="暂无招聘" />
        ) : (
          <>
            <div className="flex flex-col gap-3">
              {jobs.data.items.map((job) => (
                <div key={job.id} className="panel flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
                  <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/jobs/${job.id}`} className="text-sm font-semibold text-ink hover:text-primary">
                        {job.title}
                      </Link>
                      <JobStatusBadge status={job.status} />
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <JobTypeTag type={job.type} />
                      {job.tags.map((t) => (
                        <TagTag key={t.id} tag={t} />
                      ))}
                      <span className="text-xs text-ink2">
                        发布者 {job.publisher.name}（{ROLE_LABEL[job.publisher.role]}）
                      </span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => setTarget({ kind: 'jobs', id: job.id, title: job.title })}
                  >
                    <Trash2 size={14} /> 删除
                  </Button>
                </div>
              ))}
            </div>
            <Pagination page={page} pageSize={PAGE_SIZE} total={jobs.data.total} onChange={setPage} />
          </>
        )}
      </div>

      <GovernDeleteModal target={target} onClose={() => setTarget(null)} onDone={jobs.reload} />
    </>
  );
}

function AnnouncementsGovernPanel() {
  const [page, setPage] = useState(1);
  const [target, setTarget] = useState<Target | null>(null);

  const list = useAsync(() => repo.announcements.list({ page, pageSize: PAGE_SIZE }), [page]);

  return (
    <>
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink2">{list.data ? `共 ${list.data.total} 条公告` : '加载中…'}</p>
        <Link to="/announcements/new">
          <Button size="sm" variant="secondary">
            <FileText size={14} /> 发布公告
          </Button>
        </Link>
      </div>

      <div className="mt-4">
        {list.loading ? (
          <PageLoader />
        ) : list.error ? (
          <ErrorState message={list.error} onRetry={list.reload} />
        ) : !list.data || list.data.items.length === 0 ? (
          <EmptyState title="暂无公告" />
        ) : (
          <>
            <div className="flex flex-col gap-3">
              {list.data.items.map((a) => (
                <div key={a.id} className="panel flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <Link
                      to={`/announcements/${a.id}`}
                      className="text-sm font-semibold text-ink hover:text-primary"
                    >
                      {a.title}
                    </Link>
                    <p className="text-xs text-ink2">
                      {TIME_KIND_LABEL[a.timeKind]} {formatDateTime(a.eventAt)} · 发布者 {a.author.name}（
                      {ROLE_LABEL[a.author.role]}）
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => setTarget({ kind: 'announcements', id: a.id, title: a.title })}
                  >
                    <Trash2 size={14} /> 下架
                  </Button>
                </div>
              ))}
            </div>
            <Pagination page={page} pageSize={PAGE_SIZE} total={list.data.total} onChange={setPage} />
          </>
        )}
      </div>

      <GovernDeleteModal target={target} onClose={() => setTarget(null)} onDone={list.reload} />
    </>
  );
}

function GovernDeleteModal({
  target,
  onClose,
  onDone,
}: {
  target: Target | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState('');
  const [reasonErr, setReasonErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const close = () => {
    setReason('');
    setReasonErr(null);
    onClose();
  };

  const submit = async () => {
    if (!target) return;
    const err = validateModerationReason(reason);
    setReasonErr(err);
    if (err) return;
    setBusy(true);
    try {
      if (target.kind === 'jobs') await repo.admin.governRemoveJob(target.id, reason);
      else await repo.announcements.governRemove(target.id, reason);
      toast.success('已删除不合规内容并通知发布者');
      close();
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={!!target}
      title={target?.kind === 'jobs' ? '治理删除招聘' : '治理下架公告'}
      onClose={close}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            取消
          </Button>
          <Button variant="danger" onClick={submit} loading={busy}>
            确认删除
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm leading-relaxed text-ink2">
          删除「{target?.title}」并通知发布者，原因将写入审计日志
          {target?.kind === 'jobs' && '；相关处理中/已接受的申请会转为已失效'}。
        </p>
        <Field error={reasonErr ?? undefined} hint="1～500 字">
          <Textarea
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setReasonErr(null);
            }}
            placeholder="请填写删除原因"
            maxLength={500}
          />
        </Field>
      </div>
    </Modal>
  );
}
