import { Pencil, ShieldCheck, Trash2, Users } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { clsx } from 'clsx';
import type { Application, Job } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { ROLE_LABEL } from '@/domain/labels';
import { formatDate } from '@/domain/jobStatus';
import { ApplicationStatusBadge, JobStatusBadge } from '@/components/ui/StatusBadge';
import { QuotaProgress } from '@/components/job/QuotaProgress';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { toast } from '@/stores/toast';

type Tab = 'mine' | 'applications' | 'teams' | 'history';

const TABS: { key: Tab; label: string }[] = [
  { key: 'mine', label: '我发布的招聘' },
  { key: 'applications', label: '我提交的申请' },
  { key: 'teams', label: '进行中组队项目' },
  { key: 'history', label: '历史活动' },
];

export function ProfilePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('mine');

  const myJobs = useAsync(() => repo.jobs.listMine({ type: 'all', page: 1, pageSize: 100 }), [user]);
  const myApps = useAsync(() => repo.applications.listMine({ page: 1, pageSize: 100 }), [user]);
  const allJobs = useAsync(() => repo.jobs.list({ type: 'all', page: 1, pageSize: 200 }), [user]);

  const [withdrawTarget, setWithdrawTarget] = useState<Application | null>(null);
  const [busy, setBusy] = useState(false);

  const teams = useMemo(() => {
    const jobs = allJobs.data?.items ?? [];
    const acceptedJobIds = new Set(
      (myApps.data?.items ?? []).filter((a) => a.status === 'accepted').map((a) => a.jobId),
    );
    return jobs.filter((j) => j.status !== 'closed' && (j.publisher.id === user?.id || acceptedJobIds.has(j.id)));
  }, [allJobs.data, myApps.data, user]);

  const history = useMemo(() => {
    const jobs = allJobs.data?.items ?? [];
    const byId = new Map(jobs.map((j) => [j.id, j]));
    return (myApps.data?.items ?? [])
      .map((a) => ({ app: a, job: byId.get(a.jobId) }))
      .filter((x): x is { app: Application; job: Job } => !!x.job && x.job.status === 'closed');
  }, [allJobs.data, myApps.data]);

  if (!user) return null;

  const doWithdraw = async () => {
    if (!withdrawTarget) return;
    setBusy(true);
    try {
      await repo.applications.withdraw(withdrawTarget.id);
      toast.success('已撤回申请，简历不再对发布者展示');
      setWithdrawTarget(null);
      await myApps.reload();
      await allJobs.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '撤回失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* 个人信息卡 */}
      <div className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-6 sm:flex-row sm:items-center">
        <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-primary-soft text-2xl font-semibold text-primary">
          {user.name[0]}
        </span>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold text-ink">{user.name}</span>
            <span className="rounded-full bg-primary-soft px-2.5 py-0.5 text-xs text-primary">{ROLE_LABEL[user.role]}</span>
            {user.isAdmin && (
              <span className="flex items-center gap-1 rounded-full bg-danger-soft px-2.5 py-0.5 text-xs text-danger">
                <ShieldCheck size={13} /> 管理员
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-ink2">
            {user.role === 'student' ? '学号' : '工号'} {user.id}
            {user.college ? ` · ${user.college}` : ''}
            {user.major ? ` · ${user.major}` : ''}
          </p>
          <p className="mt-1 text-xs text-muted">身份仅在个人主页标注，业务逻辑完全一致</p>
        </div>
        <Button onClick={() => navigate('/jobs/new')}>发布招聘</Button>
      </div>

      {/* Tabs */}
      <div className="mt-6 flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
              tab === t.key
                ? 'border-primary text-primary'
                : 'border-transparent text-ink2 hover:text-ink',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'mine' && (
          <MineJobsTab
            loading={myJobs.loading}
            error={myJobs.error}
            jobs={myJobs.data?.items ?? []}
            reload={myJobs.reload}
          />
        )}
        {tab === 'applications' && (
          <MyApplicationsTab
            loading={myApps.loading}
            error={myApps.error}
            apps={myApps.data?.items ?? []}
            onWithdraw={setWithdrawTarget}
          />
        )}
        {tab === 'teams' && (
          <TeamsTab jobs={teams} isOwner={(j) => j.publisher.id === user.id} />
        )}
        {tab === 'history' && <HistoryTab items={history} />}
      </div>

      <ConfirmDialog
        open={!!withdrawTarget}
        title="撤回申请"
        description={`撤回后该申请对「${withdrawTarget?.jobTitle}」的发布者不再可见，简历文件与补充说明将被隐藏。撤回后可重新投递。`}
        confirmText="确认撤回"
        danger={false}
        loading={busy}
        onConfirm={doWithdraw}
        onCancel={() => setWithdrawTarget(null)}
      />
    </div>
  );
}

function MineJobsTab({
  loading,
  error,
  jobs,
  reload,
}: {
  loading: boolean;
  error: string | null;
  jobs: Job[];
  reload: () => void;
}) {
  const navigate = useNavigate();
  const [deleteTarget, setDeleteTarget] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <PageLoader />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (jobs.length === 0) return <EmptyState title="你还没有发布过招聘" />;

  const doDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await repo.jobs.remove(deleteTarget.id);
      toast.success('招聘已删除');
      setDeleteTarget(null);
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-ink2">仅进行中招聘可修改；删除会通知所有未拒绝申请人；可手动关闭招聘。</p>
      {jobs.map((job) => (
        <div key={job.id} className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <Link to={`/jobs/${job.id}`} className="text-sm font-semibold text-ink hover:text-primary">
                {job.title}
              </Link>
              <JobStatusBadge status={job.status} />
            </div>
            <QuotaProgress accepted={job.acceptedCount} total={job.recruitCount} />
            <p className="text-xs text-ink2">截止 {formatDate(job.deadline)} · 收到 {job.applicationCount} 条申请</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/jobs/${job.id}/applications`}>
              <Button size="sm" variant="secondary">
                <Users size={14} /> 招聘申请管理
              </Button>
            </Link>
            {job.status === 'open' && (
              <Button size="sm" variant="secondary" onClick={() => navigate(`/jobs/${job.id}/edit`)}>
                <Pencil size={14} /> 编辑修改
              </Button>
            )}
            {job.status === 'open' && (
              <Button
                size="sm"
                variant="secondary"
                onClick={async () => {
                  await repo.jobs.close(job.id);
                  toast.success('招聘已关闭');
                  reload();
                }}
              >
                手动关闭招聘
              </Button>
            )}
            <Button size="sm" variant="danger-outline" onClick={() => setDeleteTarget(job)}>
              <Trash2 size={14} /> 删除
            </Button>
          </div>
        </div>
      ))}

      <ConfirmDialog
        open={!!deleteTarget}
        title="删除招聘"
        description={`删除操作不可逆，确认删除「${deleteTarget?.title}」？`}
        confirmText="确认删除"
        loading={busy}
        onConfirm={doDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

function MyApplicationsTab({
  loading,
  error,
  apps,
  onWithdraw,
}: {
  loading: boolean;
  error: string | null;
  apps: Application[];
  onWithdraw: (a: Application) => void;
}) {
  if (loading) return <PageLoader />;
  if (error) return <ErrorState message={error} />;
  if (apps.length === 0) return <EmptyState title="你还没有提交过申请" />;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-ink2">撤回后对方无法查看你的简历文件；撤回后可重新投递。</p>
      {apps.map((app) => (
        <div key={app.id} className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex items-center gap-2">
              <Link to={`/jobs/${app.jobId}`} className="text-sm font-semibold text-ink hover:text-primary">
                {app.jobTitle}
              </Link>
              <ApplicationStatusBadge status={app.status} />
            </div>
            <p className="text-xs text-ink2">提交于 {formatDate(app.createdAt)}</p>
          </div>
          {app.status === 'pending' && (
            <Button size="sm" variant="danger-outline" onClick={() => onWithdraw(app)}>
              撤回申请
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}

function TeamsTab({ jobs, isOwner }: { jobs: Job[]; isOwner: (j: Job) => boolean }) {
  if (jobs.length === 0) return <EmptyState title="暂无进行中的组队项目" />;
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {jobs.map((job) => (
        <div key={job.id} className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-5">
          <div className="flex items-start justify-between gap-2">
            <Link to={`/jobs/${job.id}`} className="text-sm font-semibold text-ink hover:text-primary">
              {job.title}
            </Link>
            <JobStatusBadge status={job.status} />
          </div>
          <p className="line-clamp-2 text-sm text-ink2">{job.description}</p>
          <QuotaProgress accepted={job.acceptedCount} total={job.recruitCount} />
          <p className="text-xs text-ink2">报名截止：{formatDate(job.deadline)}</p>
          <div className="mt-auto flex gap-2 pt-1">
            <Link to={`/jobs/${job.id}`}>
              <Button size="sm" variant="secondary">
                查看详情
              </Button>
            </Link>
            {isOwner(job) && (
              <Link to={`/jobs/${job.id}/applications`}>
                <Button size="sm" variant="secondary">
                  管理成员
                </Button>
              </Link>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function HistoryTab({ items }: { items: { app: Application; job: Job }[] }) {
  if (items.length === 0) return <EmptyState title="暂无历史活动记录" />;
  return (
    <div className="flex flex-col gap-3">
      {items.map(({ app, job }) => {
        const success = app.status === 'accepted';
        return (
          <div key={app.id} className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">{job.title}</p>
              <p className="text-xs text-ink2">截止 {formatDate(job.deadline)} · 申请状态 {app.status === 'pending' ? '处理中' : app.status === 'accepted' ? '已接受' : app.status === 'rejected' ? '已拒绝' : '已撤回'}</p>
            </div>
            <span
              className={clsx(
                'shrink-0 rounded-full px-3 py-1 text-sm font-medium',
                success ? 'bg-success-soft text-success' : 'bg-muted-soft text-muted',
              )}
            >
              {success ? '匹配成功' : '匹配失败'}
            </span>
          </div>
        );
      })}
    </div>
  );
}
