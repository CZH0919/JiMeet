import { Briefcase, Inbox, Pencil, Plus, Send, ShieldCheck, Trash2, Users } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { clsx } from 'clsx';
import type { Application, Job } from '@/domain/models';
import { repo } from '@/data';
import { fetchAllPages } from '@/data/fetchAll';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { formatDate, formatDateTime } from '@/domain/format';
import { APPLICATION_STATUS_LABEL, ROLE_LABEL } from '@/domain/labels';
import { validateNickname } from '@/domain/validation';
import { ApplicationStatusBadge, JobStatusBadge } from '@/components/ui/StatusBadge';
import { QuotaProgress } from '@/components/job/QuotaProgress';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field, Input } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { EditApplicationDialog } from '@/components/application/EditApplicationDialog';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { toast } from '@/stores/toast';

type Tab = 'mine' | 'received' | 'applications';

const TABS: { key: Tab; label: string; icon: typeof Briefcase }[] = [
  { key: 'mine', label: '我发布的招聘', icon: Briefcase },
  { key: 'received', label: '收到的申请', icon: Inbox },
  { key: 'applications', label: '我提交的申请', icon: Send },
];

export function ProfilePage() {
  const { user, consentPrivacy, updateNickname } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') as Tab | null) ?? 'mine';
  const setTab = (next: Tab) => setParams(next === 'mine' ? {} : { tab: next }, { replace: true });

  const myJobs = useAsync(
    () => fetchAllPages((p, s) => repo.jobs.listMine({ type: 'all', page: p, pageSize: s })),
    [user?.id],
  );
  const myApps = useAsync(
    () => fetchAllPages((p, s) => repo.applications.listMine({ page: p, pageSize: s })),
    [user?.id],
  );

  // 收到的待处理申请：聚合本人每条招聘下的 processing 申请（后端无跨招聘聚合接口）
  const received = useAsync(async () => {
    if (tab !== 'received' || !myJobs.data) return [];
    const pages = await Promise.all(
      myJobs.data.map((job) =>
        fetchAllPages((p, s) =>
          repo.applications.listForJob(job.id, { page: p, pageSize: s, status: 'processing' }),
        ),
      ),
    );
    return myJobs.data.flatMap((job, i) => pages[i].map((app) => ({ job, app })));
  }, [tab, myJobs.data]);

  const [withdrawTarget, setWithdrawTarget] = useState<Application | null>(null);
  const [editTarget, setEditTarget] = useState<Application | null>(null);
  const [busy, setBusy] = useState(false);
  const [nickOpen, setNickOpen] = useState(false);
  const [nickname, setNickname] = useState(user?.name ?? '');
  const [nickErr, setNickErr] = useState<string | null>(null);

  const counts = useMemo(
    () => ({
      jobs: myJobs.data?.length ?? 0,
      apps: myApps.data?.length ?? 0,
    }),
    [myJobs.data, myApps.data],
  );

  if (!user) return null;

  const doWithdraw = async () => {
    if (!withdrawTarget) return;
    setBusy(true);
    try {
      await repo.applications.withdraw(withdrawTarget.id);
      toast.success('已撤回申请，发布者不再可查看你的简历');
      setWithdrawTarget(null);
      await myApps.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '撤回失败');
    } finally {
      setBusy(false);
    }
  };

  const openEdit = async (app: Application) => {
    try {
      // 列表接口不返回 note，修改前先取详情，避免把说明清空
      const detail = await repo.applications.detail(app.id);
      setEditTarget(detail);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '加载申请详情失败');
    }
  };

  const saveNickname = async () => {
    const err = validateNickname(nickname);
    setNickErr(err);
    if (err) return;
    try {
      await updateNickname(nickname);
      setNickOpen(false);
    } catch (err2) {
      toast.error(err2 instanceof Error ? err2.message : '保存失败');
    }
  };

  return (
    <div className="page-shell max-w-[1000px] py-8 sm:py-10">
      {/* 个人信息卡 */}
      <section className="panel flex flex-col gap-5 px-6 py-6 sm:flex-row sm:items-center">
        <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-primary-soft text-2xl font-semibold text-primary">
          {user.name.slice(0, 1)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold text-ink">{user.name}</span>
            <span className="rounded-full bg-primary-soft px-2.5 py-0.5 text-xs text-primary">
              {ROLE_LABEL[user.role]}
            </span>
            {user.isAdmin && (
              <span className="flex items-center gap-1 rounded-full bg-danger-soft px-2.5 py-0.5 text-xs text-danger">
                <ShieldCheck size={13} /> 管理员
              </span>
            )}
            <button
              onClick={() => {
                setNickname(user.name);
                setNickErr(null);
                setNickOpen(true);
              }}
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs text-ink2 transition-colors hover:bg-muted-soft hover:text-ink"
            >
              <Pencil size={12} /> 修改昵称
            </button>
          </div>
          <p className="mt-1 truncate text-sm text-ink2">{user.email}</p>
        </div>
        <Button className="shrink-0" onClick={() => navigate('/jobs/new')}>
          <Plus size={15} /> 发布招聘
        </Button>
      </section>

      {/* 未确认个人信息处理告知提醒 */}
      {!user.privacyConsented && (
        <div className="mt-4 flex flex-col gap-3 rounded-lg border border-warning/30 bg-warning-soft px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm leading-relaxed text-ink2">
            确认《个人信息处理告知》后才能投递简历。
          </p>
          <Button
            size="sm"
            variant="secondary"
            className="shrink-0"
            onClick={() => void consentPrivacy()}
          >
            我已阅读并确认
          </Button>
        </div>
      )}

      {/* 概览 */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="panel px-5 py-4">
          <p className="text-xs text-ink2">我发布的招聘</p>
          <p className="mt-1 text-xl font-semibold text-ink">{counts.jobs}</p>
        </div>
        <div className="panel px-5 py-4">
          <p className="text-xs text-ink2">我提交的申请</p>
          <p className="mt-1 text-xl font-semibold text-ink">{counts.apps}</p>
        </div>
      </div>

      {/* 管理员入口：与基础身份功能分开（SRS 2.3） */}
      {user.isAdmin && (
        <div className="mt-4 flex flex-col gap-3 rounded-lg border border-danger/20 bg-danger-soft/30 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-danger">管理员功能</p>
            <p className="mt-0.5 text-xs text-ink2">发布竞赛与活动公告，或处置不合规内容。</p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Link to="/announcements/new">
              <Button size="sm" variant="secondary">
                发布公告
              </Button>
            </Link>
            <Link to="/admin">
              <Button size="sm" variant="danger-outline">
                内容治理后台
              </Button>
            </Link>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="mt-6 flex flex-wrap gap-1 border-b border-line">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={clsx(
              '-mb-px flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm transition-colors',
              tab === key
                ? 'border-primary font-medium text-primary'
                : 'border-transparent text-ink2 hover:text-ink',
            )}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      <div className="mt-5">
        {tab === 'mine' && (
          <MineJobsTab loading={myJobs.loading} error={myJobs.error} jobs={myJobs.data ?? []} reload={myJobs.reload} />
        )}

        {tab === 'received' && (
          <ReceivedTab
            loading={myJobs.loading || received.loading}
            error={received.error}
            items={received.data ?? []}
            reload={received.reload}
          />
        )}

        {tab === 'applications' && (
          <MyApplicationsTab
            loading={myApps.loading}
            error={myApps.error}
            apps={myApps.data ?? []}
            onWithdraw={setWithdrawTarget}
            onEdit={(a) => void openEdit(a)}
            reload={myApps.reload}
          />
        )}
      </div>

      <ConfirmDialog
        open={!!withdrawTarget}
        title="撤回申请"
        description={`撤回后「${withdrawTarget?.jobTitle}」的发布者将不再看到你的简历与补充说明，之后可重新投递。`}
        confirmText="确认撤回"
        danger={false}
        loading={busy}
        onConfirm={doWithdraw}
        onCancel={() => setWithdrawTarget(null)}
      />

      {editTarget && (
        <EditApplicationDialog
          app={editTarget}
          open={!!editTarget}
          onClose={() => setEditTarget(null)}
          onSubmitted={() => void myApps.reload()}
        />
      )}

      <Modal
        open={nickOpen}
        title="修改昵称"
        onClose={() => setNickOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setNickOpen(false)}>
              取消
            </Button>
            <Button onClick={saveNickname}>保存</Button>
          </>
        }
      >
        <Field label="昵称" required error={nickErr ?? undefined} hint="1～32 字，展示给其他用户；姓名与邮箱不可在此修改">
          <Input
            value={nickname}
            onChange={(e) => {
              setNickname(e.target.value);
              setNickErr(null);
            }}
            maxLength={32}
            invalid={!!nickErr}
          />
        </Field>
      </Modal>
    </div>
  );
}

/* ------------------------------- 我发布的招聘 ------------------------------- */

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
  if (jobs.length === 0) {
    return (
      <EmptyState
        title="你还没有发布过招聘"
        action={
          <Link to="/jobs/new">
            <Button size="sm">去发布</Button>
          </Link>
        }
      />
    );
  }

  const doDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await repo.jobs.remove(deleteTarget.id);
      toast.success('招聘已删除，相关申请已失效');
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
      <p className="text-xs text-ink2">进行中的招聘可编辑或删除；删除会使相关申请失效。</p>
      {jobs.map((job) => (
        <div key={job.id} className="panel flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={`/jobs/${job.id}`} className="text-sm font-semibold text-ink hover:text-primary">
                {job.title}
              </Link>
              <JobStatusBadge status={job.status} />
            </div>
            <div className="max-w-[260px]">
              <QuotaProgress accepted={job.acceptedCount} total={job.maxHeadcount} showLabel={false} />
            </div>
            <p className="text-xs text-ink2">
              截止 {formatDate(job.deadline)} · 已接受 {job.acceptedCount} / {job.maxHeadcount} 人 · 发布{' '}
              {formatDate(job.createdAt)}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/jobs/${job.id}/applications`}>
              <Button size="sm" variant="secondary">
                <Users size={14} /> 申请管理
              </Button>
            </Link>
            {job.status === 'open' && (
              <Button size="sm" variant="secondary" onClick={() => navigate(`/jobs/${job.id}/edit`)}>
                <Pencil size={14} /> 编辑
              </Button>
            )}
            {job.status === 'open' && (
              <Button
                size="sm"
                variant="secondary"
                onClick={async () => {
                  try {
                    await repo.jobs.close(job.id);
                    toast.success('招聘已关闭');
                    reload();
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : '关闭失败');
                  }
                }}
              >
                关闭
              </Button>
            )}
            {job.status === 'open' && (
              <Button size="sm" variant="danger-outline" onClick={() => setDeleteTarget(job)}>
                <Trash2 size={14} /> 删除
              </Button>
            )}
          </div>
        </div>
      ))}

      <ConfirmDialog
        open={!!deleteTarget}
        title="删除招聘"
        description={`删除「${deleteTarget?.title}」不可恢复：处理中与已接受的申请将转为已失效，相关申请人会收到站内通知。`}
        confirmText="确认删除"
        loading={busy}
        onConfirm={doDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

/* -------------------------------- 收到的申请 -------------------------------- */

function ReceivedTab({
  loading,
  error,
  items,
  reload,
}: {
  loading: boolean;
  error: string | null;
  items: { job: Job; app: Application }[];
  reload: () => void;
}) {
  if (loading) return <PageLoader />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (items.length === 0) {
    return <EmptyState title="暂无待处理的申请" />;
  }

  return (
    <div className="flex flex-col gap-3">
      {items.map(({ job, app }) => (
        <div key={app.id} className="panel flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-ink">{app.applicant.name}</span>
              <span className="rounded-full bg-muted-soft px-2 py-0.5 text-xs text-ink2">
                {ROLE_LABEL[app.applicant.role]}
              </span>
              {app.modified && (
                <span className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning">
                  <span className="h-1.5 w-1.5 rounded-full bg-warning" /> 已修改
                </span>
              )}
            </div>
            <p className="mt-1 truncate text-xs text-ink2">
              申请「{job.title}」· {formatDateTime(app.createdAt)}
            </p>
          </div>
          <Link to={`/jobs/${job.id}/applications`}>
            <Button size="sm" variant="secondary">
              去处理
            </Button>
          </Link>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------- 我提交的申请 ------------------------------- */

function MyApplicationsTab({
  loading,
  error,
  apps,
  onWithdraw,
  onEdit,
  reload,
}: {
  loading: boolean;
  error: string | null;
  apps: Application[];
  onWithdraw: (a: Application) => void;
  onEdit: (a: Application) => void;
  reload: () => void;
}) {
  if (loading) return <PageLoader />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (apps.length === 0) {
    return (
      <EmptyState
        title="你还没有提交过申请"
        action={
          <Link to="/jobs">
            <Button size="sm">去逛招聘</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-ink2">处理中的申请可修改或撤回。</p>
      {apps.map((app) => (
        <div key={app.id} className="panel flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {app.jobDeleted ? (
                <span className="text-sm font-semibold text-ink">{app.jobTitle}</span>
              ) : (
                <Link to={`/jobs/${app.jobId}`} className="text-sm font-semibold text-ink hover:text-primary">
                  {app.jobTitle}
                </Link>
              )}
              <ApplicationStatusBadge status={app.status} />
              {app.jobDeleted && (
                <span className="rounded-full bg-muted-soft px-2 py-0.5 text-xs text-muted">招聘已删除</span>
              )}
            </div>
            <p className="mt-1 text-xs text-ink2">
              提交于 {formatDateTime(app.createdAt)}
              {app.decidedAt && ` · 处理于 ${formatDateTime(app.decidedAt)}`}
            </p>
            {app.status === 'invalid' && (
              <p className="mt-1 text-xs text-muted">该招聘已被删除，申请已失效；你可继续下载本人简历。</p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {app.canModify && (
              <Button size="sm" variant="secondary" onClick={() => onEdit(app)}>
                <Pencil size={14} /> 修改申请
              </Button>
            )}
            {app.canWithdraw && (
              <Button size="sm" variant="danger-outline" onClick={() => onWithdraw(app)}>
                撤回
              </Button>
            )}
            {app.canDownloadResume && app.resume && (
              <Button
                size="sm"
                variant="secondary"
                onClick={async () => {
                  try {
                    await repo.applications.downloadResume(app.id);
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : '下载失败');
                  }
                }}
              >
                下载简历
              </Button>
            )}
            {!app.canModify && !app.canWithdraw && (
              <span className="text-xs text-muted">{APPLICATION_STATUS_LABEL[app.status]}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
