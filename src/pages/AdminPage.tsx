import { CheckCircle2, Clock3, FileText, RefreshCw, Search, ShieldAlert, Trash2, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { clsx } from 'clsx';
import type { ClaimedSubmission, PendingSubmission } from '@/domain/models';
import { repo } from '@/data';
import { ApiError } from '@/data/http/client';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { usePendingSubmissionCount } from '@/features/useSubmissionReview';
import { formatDateTime } from '@/domain/format';
import { ROLE_LABEL, TIME_KIND_LABEL } from '@/domain/labels';
import { validateModerationReason, validateRejectReason } from '@/domain/validation';
import { JobStatusBadge } from '@/components/ui/StatusBadge';
import { JobTypeTag, TagTag } from '@/components/job/JobTypeTag';
import { Button } from '@/components/ui/Button';
import { Field, Textarea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { EmptyState, ErrorState, InfoBanner, PageLoader } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';
import { toast } from '@/stores/toast';

type Tab = 'jobs' | 'announcements' | 'review';

interface Target {
  kind: 'jobs' | 'announcements';
  id: string;
  title: string;
}

const PAGE_SIZE = 20;
const REVIEW_PAGE_SIZE = 10;

export function AdminPage() {
  const [params, setParams] = useSearchParams();
  const user = useAuth().user;
  const tab = (params.get('tab') as Tab | null) ?? 'jobs';
  const pending = usePendingSubmissionCount();

  const setTab = (next: Tab) => setParams(next === 'jobs' ? {} : { tab: next }, { replace: true });

  const tabs: { key: Tab; label: string; badge?: number }[] = [
    { key: 'jobs', label: '招聘治理' },
    { key: 'announcements', label: '公告治理' },
    { key: 'review', label: '公告审核', badge: pending.count },
  ];

  return (
    <div className="page-shell py-8 sm:py-10">
      <h1 className="flex items-center gap-2 text-xl font-bold text-ink">
        <ShieldAlert size={20} className="text-danger" /> 内容治理后台
      </h1>
      <p className="mt-1 text-sm text-ink2">
        删除需填写原因并记入审计日志；不读取申请、简历与聊天内容。
      </p>

      <div className="mt-6 flex gap-1 border-b border-line">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              '-mb-px flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm transition-colors',
              tab === t.key
                ? 'border-danger font-medium text-danger'
                : 'border-transparent text-ink2 hover:text-ink',
            )}
          >
            {t.label}
            {!!t.badge && t.badge > 0 && (
              <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-none text-white">
                {t.badge > 99 ? '99+' : t.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="mt-5">
        {tab === 'jobs' && <JobsGovernPanel />}
        {tab === 'announcements' && <AnnouncementsGovernPanel />}
        {tab === 'review' && user && (
          <PendingReviewPanel userId={user.id} onChanged={() => void pending.refresh()} />
        )}
      </div>
    </div>
  );
}

/* -------------------------------- 招聘治理 -------------------------------- */

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

      <GovernDeleteModal
        target={target}
        onClose={() => setTarget(null)}
        onDone={jobs.reload}
      />
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

      <GovernDeleteModal
        target={target}
        onClose={() => setTarget(null)}
        onDone={list.reload}
      />
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

/* ------------------------------- 公告审核工作台 ------------------------------- */

function PendingReviewPanel({ userId, onChanged }: { userId: string; onChanged: () => void }) {
  const [page, setPage] = useState(1);
  const [tick, setTick] = useState(0);
  const list = useAsync(
    () => repo.announcements.listPendingSubmissions({ page, pageSize: REVIEW_PAGE_SIZE }),
    [page, tick],
  );
  const [active, setActive] = useState<{ row: PendingSubmission; claim: ClaimedSubmission } | null>(null);
  const [claimingId, setClaimingId] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<{ row: PendingSubmission; claim: ClaimedSubmission } | null>(null);

  const refresh = () => setTick((t) => t + 1);

  const claim = async (row: PendingSubmission) => {
    setClaimingId(row.id);
    try {
      // 已由本人领取时后端返回原批次与原截止时间，可安全重试
      const claimed = await repo.announcements.claimSubmission(row.id);
      setActive({ row, claim: claimed });
      // 刷新列表，让其他管理员和自己的列表都显示当前领取状态
      refresh();
    } catch (e) {
      if (e instanceof ApiError && e.code === 'SUBMISSION_LOCKED') {
        toast.info('该投稿已被其他管理员领取或你的领取已失效，已刷新列表');
        refresh();
        onChanged();
      } else {
        toast.error(e instanceof Error ? e.message : '领取失败');
      }
    } finally {
      setClaimingId(null);
    }
  };

  const release = async () => {
    if (!active) return;
    setClaimingId(active.row.id);
    try {
      await repo.announcements.releaseSubmission(active.row.id, active.claim.claimId);
      toast.info('已交回该投稿，其他管理员可继续处理');
      setActive(null);
      refresh();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '交回失败');
      refresh();
    } finally {
      setClaimingId(null);
    }
  };

  const approve = async () => {
    if (!active) return;
    setClaimingId(active.row.id);
    try {
      const result = await repo.announcements.approveSubmission(active.row.id, active.claim.claimId);
      toast.success(
        result.announcementId ? '投稿已通过并发布，公告已展示在首页' : '投稿已通过并发布',
      );
      setActive(null);
      refresh();
      onChanged();
    } catch (e) {
      if (e instanceof ApiError && (e.code === 'SUBMISSION_LOCKED' || e.code === 'SUBMISSION_ALREADY_PROCESSED')) {
        toast.info(e.message);
        setActive(null);
        refresh();
        onChanged();
      } else {
        toast.error(e instanceof Error ? e.message : '发布失败');
      }
    } finally {
      setClaimingId(null);
    }
  };

  const rows = list.data?.items ?? [];

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-ink2">
          {list.data ? `待审 ${list.data.total} 条` : '加载中…'} · 按提交时间正序，超过 24 小时的优先
        </p>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={refresh}>
            <RefreshCw size={14} /> 刷新
          </Button>
        </div>
      </div>

      <div className="mt-4">
        <InfoBanner>
          先领取后处理（15 分钟）；通过即按原文发布，驳回需填写理由。
        </InfoBanner>
      </div>

      <div className="mt-4">
        {list.loading ? (
          <PageLoader />
        ) : list.error ? (
          <ErrorState message={list.error} onRetry={list.reload} />
        ) : rows.length === 0 ? (
          <EmptyState title="暂无待审投稿" description="用户投稿将在此显示。" />
        ) : (
          <>
            <div className="flex flex-col gap-3">
              {rows.map((row) => {
                const mine = row.claimedBy?.id === userId;
                const others = row.claimedBy && !mine ? row.claimedBy : null;
                return (
                  <div
                    key={row.id}
                    className={clsx(
                      'panel flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center',
                      row.overdue && 'border-danger/35 bg-danger-soft/20',
                    )}
                  >
                    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-ink">{row.title}</span>
                        {row.overdue && (
                          <span className="rounded-full bg-danger-soft px-2 py-0.5 text-xs font-medium text-danger">
                            超过 24 小时未处理
                          </span>
                        )}
                        {mine && (
                          <span className="rounded-full bg-primary-soft px-2 py-0.5 text-xs text-primary">
                            你已领取
                          </span>
                        )}
                        {others && (
                          <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning">
                            {others.name} 审核中
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-ink2">
                        投稿人 {row.submitter.name}（{ROLE_LABEL[row.submitter.role]}） · 提交于{' '}
                        {formatDateTime(row.submittedAt)} · {TIME_KIND_LABEL[row.timeKind]}{' '}
                        {formatDateTime(row.eventAt)}
                      </p>
                      <p className="line-clamp-2 text-xs leading-relaxed text-muted">{row.content}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {row.claimedUntil && (mine || others) && (
                        <ClaimCountdown until={row.claimedUntil} />
                      )}
                      {mine ? (
                        <Button size="sm" variant="secondary" loading={claimingId === row.id} onClick={() => void claim(row)}>
                          继续处理
                        </Button>
                      ) : others ? (
                        <Button size="sm" variant="secondary" disabled>
                          他人处理中
                        </Button>
                      ) : (
                        <Button size="sm" loading={claimingId === row.id} onClick={() => void claim(row)}>
                          <Clock3 size={14} /> 领取并审核
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <Pagination page={page} pageSize={REVIEW_PAGE_SIZE} total={list.data?.total ?? 0} onChange={setPage} />
          </>
        )}
      </div>

      {/* 审核详情：通过 / 驳回 / 交回 */}
      <Modal
        open={!!active}
        title="审核投稿"
        description={active ? `投稿人 ${active.row.submitter.name} · ${formatDateTime(active.row.submittedAt)}` : undefined}
        onClose={() => setActive(null)}
        width="max-w-2xl"
        bodyClassName="max-h-[72vh] overflow-y-auto px-6 py-5"
        footer={
          active ? (
            <>
              <Button variant="secondary" onClick={() => setActive(null)} disabled={!!claimingId}>
                稍后再处理
              </Button>
              <Button variant="secondary" onClick={() => void release()} loading={claimingId === active.row.id}>
                交回待审池
              </Button>
              <Button variant="danger-outline" onClick={() => setRejecting(active)} disabled={!!claimingId}>
                <XCircle size={14} /> 驳回
              </Button>
              <Button onClick={() => void approve()} loading={claimingId === active.row.id}>
                <CheckCircle2 size={14} /> 通过并发布
              </Button>
            </>
          ) : null
        }
      >
        {active && (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-ink">{active.row.title}</h2>
              <span className="rounded-full bg-muted-soft px-2 py-0.5 text-xs text-ink2">
                {TIME_KIND_LABEL[active.row.timeKind]} {formatDateTime(active.row.eventAt)}
              </span>
              <ClaimCountdown until={active.claim.claimedUntil} />
            </div>
            {active.row.linkUrl && (
              <a
                href={active.row.linkUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="break-all text-xs text-primary hover:underline"
              >
                {active.row.linkUrl}
              </a>
            )}
            <p className="whitespace-pre-wrap rounded-md bg-page px-4 py-3 text-sm leading-relaxed text-ink2">
              {active.row.content}
            </p>
            <p className="text-xs leading-relaxed text-muted">
              通过后按原文发布，署名为审核管理员；如需修改内容请驳回并说明原因。
            </p>
          </div>
        )}
      </Modal>

      <RejectSubmissionModal
        target={rejecting}
        onClose={() => setRejecting(null)}
        onDone={() => {
          setRejecting(null);
          setActive(null);
          refresh();
          onChanged();
        }}
      />
    </>
  );
}

function RejectSubmissionModal({
  target,
  onClose,
  onDone,
}: {
  target: { row: PendingSubmission; claim: ClaimedSubmission } | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const close = () => {
    setReason('');
    setErr(null);
    onClose();
  };

  const submit = async () => {
    if (!target) return;
    const message = validateRejectReason(reason);
    setErr(message);
    if (message) return;
    setBusy(true);
    try {
      await repo.announcements.rejectSubmission(target.row.id, target.claim.claimId, reason);
      toast.success('已驳回投稿，投稿人会收到含理由的站内通知');
      setReason('');
      onDone();
    } catch (e) {
      if (e instanceof ApiError && (e.code === 'SUBMISSION_LOCKED' || e.code === 'SUBMISSION_ALREADY_PROCESSED')) {
        toast.info(e.message);
        onDone();
      } else {
        toast.error(e instanceof Error ? e.message : '驳回失败');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={!!target}
      title="驳回投稿"
      onClose={close}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            取消
          </Button>
          <Button variant="danger" onClick={() => void submit()} loading={busy}>
            确认驳回
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm leading-relaxed text-ink2">
          驳回「{target?.row.title}」，理由会随站内通知发送给投稿人。
        </p>
        <Field label="驳回理由" required error={err ?? undefined} hint="1～500 字">
          <Textarea
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setErr(null);
            }}
            placeholder="请说明驳回原因"
            maxLength={500}
            autoFocus
          />
        </Field>
      </div>
    </Modal>
  );
}

/** 领取剩余时间：每秒刷新，到期显示可被接手 */
function ClaimCountdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const ms = new Date(until).getTime() - now;
  if (Number.isNaN(ms)) return null;
  if (ms <= 0) {
    return <span className="text-xs text-muted">领取已到期</span>;
  }
  const total = Math.ceil(ms / 1000);
  const mm = String(Math.floor(total / 60)).padStart(2, '0');
  const ss = String(total % 60).padStart(2, '0');
  return (
    <span className="inline-flex items-center gap-1 text-xs text-ink2">
      <Clock3 size={12} /> 剩余 {mm}:{ss}
    </span>
  );
}
