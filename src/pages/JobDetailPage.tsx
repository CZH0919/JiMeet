import {
  ArrowLeft,
  CalendarClock,
  Clock3,
  Pencil,
  ShieldAlert,
  Trash2,
  UserRound,
  Users,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { canApply, isExpired, PRIVACY_NOT_CONSENTED } from '@/domain/jobStatus';
import { can } from '@/domain/permissions';
import { formatDateTime, remainingTime } from '@/domain/format';
import { APPLICATION_STATUS_LABEL, ROLE_LABEL } from '@/domain/labels';
import { validateModerationReason } from '@/domain/validation';
import { JobTypeTag, TagTag } from '@/components/job/JobTypeTag';
import { QuotaProgress } from '@/components/job/QuotaProgress';
import { JobStatusBadge } from '@/components/ui/StatusBadge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Field, Textarea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { ApplyDialog } from '@/components/application/ApplyDialog';
import { toast } from '@/stores/toast';

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: job, loading, error, reload } = useAsync(() => repo.jobs.detail(id!), [id]);

  const [applyOpen, setApplyOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [governOpen, setGovernOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [reasonErr, setReasonErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const decision = useMemo(() => (job ? canApply(job, user) : { ok: false, reason: '' }), [job, user]);

  if (loading) return <PageLoader />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!job) return null;

  // 「未确认个人信息处理告知」是可在申请弹窗内完成确认的软阻塞，不能因此禁用按钮
  const privacyBlock =
    job.permissions?.applyBlockedCode === PRIVACY_NOT_CONSENTED && job.status === 'open' && !isExpired(job);
  const applyOk = job.permissions ? job.permissions.canApply || privacyBlock : decision.ok;
  const applyReason = job.permissions?.applyBlockedReason || (decision.ok ? '' : decision.reason);

  const canEdit = job.permissions ? job.permissions.canEdit : can.editJob(user, job);
  const canDeleteOwn = job.permissions ? job.permissions.canDelete : can.deleteJob(user, job);
  const canClose = job.permissions ? job.permissions.canClose : false;
  const canViewApps = job.permissions ? job.permissions.canViewApplications : can.manageApps(user, job);
  const canGovern = job.permissions?.canGovernDelete ?? false;
  const isPublisher = !!user && user.id === job.publisher.id;

  const doClose = async () => {
    setBusy(true);
    try {
      await repo.jobs.close(job.id);
      toast.success('招聘已关闭，不再接受新申请');
      setCloseOpen(false);
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    setBusy(true);
    try {
      await repo.jobs.remove(job.id);
      toast.success('招聘已删除，相关申请已失效');
      navigate('/jobs', { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败');
    } finally {
      setBusy(false);
      setDeleteOpen(false);
    }
  };

  const doGovern = async () => {
    const err = validateModerationReason(reason);
    setReasonErr(err);
    if (err) return;
    setBusy(true);
    try {
      await repo.admin.governRemoveJob(job.id, reason);
      toast.success('已删除不合规内容，并通知发布者');
      setGovernOpen(false);
      navigate('/admin', { replace: true });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-shell max-w-[1100px] py-8 sm:py-10">
      <Link
        to="/jobs"
        className="mb-4 inline-flex items-center gap-1 text-sm text-ink2 transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} /> 返回招聘列表
      </Link>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        {/* 主体 */}
        <article className="panel px-6 py-7 sm:px-8">
          <div className="flex items-start justify-between gap-3">
            <h1 className="min-w-0 flex-1 text-2xl font-bold leading-snug tracking-tight text-ink">
              {job.title}
            </h1>
            <span className="shrink-0 pt-1">
              <JobStatusBadge status={job.status} />
            </span>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <JobTypeTag type={job.type} />
            {job.tags.map((t) => (
              <TagTag key={t.id} tag={t} />
            ))}
            {job.isDeleted && (
              <span className="rounded-full bg-danger-soft px-2.5 py-0.5 text-xs text-danger">已删除</span>
            )}
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 rounded-md bg-page px-5 py-4 sm:grid-cols-3">
            <InfoItem
              icon={<CalendarClock size={15} />}
              label="截止时间"
              value={formatDateTime(job.deadline)}
              hint={`剩余 ${remainingTime(job.deadline)}`}
            />
            <InfoItem
              icon={<Users size={15} />}
              label="计划招募"
              value={job.minHeadcount ? `${job.minHeadcount}–${job.maxHeadcount} 人` : `${job.maxHeadcount} 人`}
              hint={`已接受 ${job.acceptedCount} 人`}
            />
            <InfoItem
              icon={<Clock3 size={15} />}
              label="发布时间"
              value={formatDateTime(job.createdAt)}
              hint={`更新于 ${formatDateTime(job.updatedAt)}`}
            />
          </div>

          <section className="mt-7">
            <h2 className="text-base font-semibold text-ink">需求与补充说明</h2>
            <p className="mt-3 whitespace-pre-wrap text-[15px] leading-8 text-ink2">{job.description}</p>
          </section>
        </article>

        {/* 侧栏 */}
        <aside className="flex flex-col gap-4">
          <div className="panel px-5 py-5">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary">
                {job.publisher.name.slice(0, 1)}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink">{job.publisher.name}</p>
                <p className="mt-0.5 flex items-center gap-1 text-xs text-ink2">
                  <UserRound size={12} /> {ROLE_LABEL[job.publisher.role]}
                </p>
              </div>
            </div>

            <div className="mt-5">
              <QuotaProgress accepted={job.acceptedCount} total={job.maxHeadcount} />
            </div>

            <div className="mt-5 border-t border-line pt-5">
              {job.myApplicationStatus ? (
                <div className="rounded-md bg-primary-soft px-4 py-3 text-sm text-primary">
                  你已申请该招聘 · 当前状态「{APPLICATION_STATUS_LABEL[job.myApplicationStatus]}」
                  <Link
                    to="/me?tab=applications"
                    className="mt-1 block text-xs font-medium underline-offset-2 hover:underline"
                  >
                    查看我的申请记录
                  </Link>
                </div>
              ) : applyOk ? (
                <>
                  <Button size="lg" className="w-full" onClick={() => setApplyOpen(true)}>
                    申请加入
                  </Button>
                </>
              ) : (
                <>
                  <Button size="lg" className="w-full" disabled>
                    申请加入
                  </Button>
                  {applyReason && <p className="mt-2 text-center text-xs text-ink2">{applyReason}</p>}
                </>
              )}
            </div>
          </div>

          {/* 发布者管理区 */}
          {(isPublisher || canViewApps) && (
            <div className="panel px-5 py-5">
              <p className="text-sm font-semibold text-ink">发布者管理</p>
              <div className="mt-3 flex flex-col gap-2">
                {canViewApps && (
                  <Link to={`/jobs/${job.id}/applications`}>
                    <Button variant="secondary" className="w-full">
                      <Users size={15} /> 招聘申请管理（{job.applicationCount}）
                    </Button>
                  </Link>
                )}
                {canEdit && (
                  <Link to={`/jobs/${job.id}/edit`}>
                    <Button variant="secondary" className="w-full">
                      <Pencil size={15} /> 编辑修改
                    </Button>
                  </Link>
                )}
                {canClose && (
                  <Button variant="secondary" className="w-full" onClick={() => setCloseOpen(true)}>
                    手动关闭招聘
                  </Button>
                )}
                {canDeleteOwn && (
                  <Button variant="danger-outline" className="w-full" onClick={() => setDeleteOpen(true)}>
                    <Trash2 size={15} /> 删除招聘
                  </Button>
                )}
                {!canEdit && !canClose && !canDeleteOwn && (
                  <p className="text-xs leading-relaxed text-muted">该招聘已结束，不可再编辑或关闭。</p>
                )}
              </div>
            </div>
          )}
        </aside>
      </div>

      {/* 管理员治理区（独立、红色、底部；SRS 2.3 要求与基础身份入口分离） */}
      {canGovern && (
        <section className="mt-5 rounded-lg border border-danger/25 bg-danger-soft/40 px-6 py-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-danger">
            <ShieldAlert size={16} /> 内容治理
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-ink2">
            删除不合规内容需填写原因并记入审计日志；受影响申请将失效并通知申请人。
          </p>
          <Button variant="danger" size="sm" className="mt-3" onClick={() => setGovernOpen(true)}>
            <Trash2 size={14} /> 删除该招聘
          </Button>
        </section>
      )}

      <ApplyDialog job={job} open={applyOpen} onClose={() => setApplyOpen(false)} onSubmitted={reload} />

      <ConfirmDialog
        open={closeOpen}
        title="关闭招聘"
        description={`关闭后「${job.title}」不再接受新申请，已有申请可在关闭后 7 天内继续处理。`}
        confirmText="确认关闭"
        danger={false}
        loading={busy}
        onConfirm={doClose}
        onCancel={() => setCloseOpen(false)}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="删除招聘"
        description={`删除「${job.title}」不可恢复：处理中与已接受的申请将转为已失效并通知申请人，发布者将失去简历访问权限。`}
        confirmText="确认删除"
        loading={busy}
        onConfirm={doDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      <Modal
        open={governOpen}
        title="删除不合规内容"
        onClose={() => setGovernOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setGovernOpen(false)}>
              取消
            </Button>
            <Button variant="danger" onClick={doGovern} loading={busy}>
              确认删除
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm leading-relaxed text-ink2">
            你正在删除「{job.title}」。该操作会通知发布者并记入审计日志。
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
    </div>
  );
}

function InfoItem({
  icon,
  label,
  value,
  hint,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="flex items-center gap-1.5 text-xs text-ink2">
        {icon}
        {label}
      </span>
      <span className="text-sm font-medium text-ink">{value}</span>
      {hint && <span className="text-[11px] text-muted">{hint}</span>}
    </div>
  );
}
