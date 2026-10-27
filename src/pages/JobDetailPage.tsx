import { CalendarClock, Pencil, ShieldAlert, Trash2, Users } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { canApply, formatDateTime } from '@/domain/jobStatus';
import { can } from '@/domain/permissions';
import { ROLE_LABEL } from '@/domain/labels';
import { FieldTag, JobTypeTag } from '@/components/job/JobTypeTag';
import { QuotaProgress } from '@/components/job/QuotaProgress';
import { JobStatusBadge } from '@/components/ui/StatusBadge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Modal } from '@/components/ui/Modal';
import { Field, Textarea } from '@/components/ui/Field';
import { ApplyDialog } from '@/components/application/ApplyDialog';
import { validateModerationReason } from '@/domain/validation';
import { toast } from '@/stores/toast';

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: job, loading, error, reload } = useAsync(() => repo.jobs.detail(id!), [id]);

  const [applyOpen, setApplyOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [moderateOpen, setModerateOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [reasonErr, setReasonErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [affected, setAffected] = useState<{ pending: number; accepted: number }>({ pending: 0, accepted: 0 });

  const decision = useMemo(() => (job ? canApply(job, user) : { ok: false, reason: '' }), [job, user]);

  if (loading) return <PageLoader />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!job) return null;

  const isOwner = can.editJob(user, job);
  const isModerator = can.moderateJob(user, job);

  const fetchAffected = async () => {
    try {
      const page = await repo.applications.listForJob(job.id, { page: 1, pageSize: 200 });
      setAffected({
        pending: page.items.filter((a) => a.status === 'pending').length,
        accepted: page.items.filter((a) => a.status === 'accepted').length,
      });
    } catch {
      setAffected({ pending: 0, accepted: 0 });
    }
    setDeleteOpen(true);
  };

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
      toast.success('招聘已删除');
      navigate('/', { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败');
    } finally {
      setBusy(false);
      setDeleteOpen(false);
    }
  };

  const doModerate = async () => {
    const err = validateModerationReason(reason);
    setReasonErr(err);
    if (err) return;
    setBusy(true);
    try {
      await repo.admin.removeJobWithReason(job.id, reason);
      toast.success('已删除不合规内容，并通知发布者');
      setModerateOpen(false);
      navigate('/admin', { replace: true });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="rounded-xl border border-line bg-surface p-8 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h1 className="text-2xl font-semibold text-ink">{job.title}</h1>
          <JobStatusBadge status={job.status} />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <JobTypeTag type={job.type} />
          <FieldTag field={job.field} />
          <span className="text-sm text-ink2">发布者 {job.publisher.name}（{ROLE_LABEL[job.publisher.role]}）</span>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 rounded-lg bg-page p-5 sm:grid-cols-3">
          <InfoItem icon={<CalendarClock size={16} />} label="截止时间" value={formatDateTime(job.deadline)} />
          <InfoItem icon={<Users size={16} />} label="计划招募人数" value={`${job.recruitCount} 人`} />
          <div className="flex flex-col gap-1">
            <span className="text-xs text-ink2">当前已接收人数</span>
            <QuotaProgress accepted={job.acceptedCount} total={job.recruitCount} />
          </div>
        </div>

        <div className="mt-6">
          <h2 className="text-base font-semibold text-ink">需求与补充说明</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink2">{job.description}</p>
          {job.requirement && (
            <div className="mt-3 rounded-md border-l-2 border-primary bg-primary-soft px-4 py-3 text-sm text-ink2">
              {job.requirement}
            </div>
          )}
        </div>

        <div className="mt-6 text-xs text-muted">发布于 {formatDateTime(job.createdAt)}</div>

        {/* 申请入口（学生） */}
        <div className="mt-6 border-t border-line pt-6">
          {job.myApplicationStatus ? (
            <div className="rounded-md bg-primary-soft px-4 py-3 text-sm text-primary">
              你已申请该招聘 · 当前状态「{job.myApplicationStatus === 'pending' ? '处理中' : job.myApplicationStatus}」
            </div>
          ) : decision.ok ? (
            <div className="flex flex-col items-start gap-2">
              <Button size="lg" onClick={() => setApplyOpen(true)}>
                申请加入
              </Button>
              <p className="text-xs text-ink2">仅进行中状态可投递申请</p>
            </div>
          ) : (
            <div className="flex flex-col items-start gap-2">
              <Button size="lg" disabled>
                申请加入
              </Button>
              <p className="text-xs text-ink2">{decision.reason}</p>
            </div>
          )}
        </div>

        {/* 发布者管理区 */}
        {isOwner && (
          <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-line pt-6">
            <Link to={`/jobs/${job.id}/edit`}>
              <Button variant="secondary">
                <Pencil size={15} /> 编辑修改
              </Button>
            </Link>
            <Link to={`/jobs/${job.id}/applications`}>
              <Button variant="secondary">
                <Users size={15} /> 招聘申请管理（{job.applicationCount}）
              </Button>
            </Link>
            {job.status === 'open' && (
              <Button variant="secondary" onClick={() => setCloseOpen(true)}>
                手动关闭招聘
              </Button>
            )}
            <Button variant="danger-outline" onClick={fetchAffected}>
              <Trash2 size={15} /> 删除
            </Button>
          </div>
        )}
      </div>

      {/* 管理员治理区（独立、红色、底部） */}
      {isModerator && (
        <div className="mt-6 rounded-xl border-2 border-danger/40 bg-danger-soft/40 p-6">
          <h2 className="flex items-center gap-2 text-base font-semibold text-danger">
            <ShieldAlert size={18} /> 内容治理
          </h2>
          <p className="mt-1 text-sm text-ink2">
            该内容由 {job.publisher.name} 发布。管理员仅可删除不合规内容并填写原因，不可编辑正文。
          </p>
          <Button variant="danger" className="mt-4" onClick={() => setModerateOpen(true)}>
            <Trash2 size={15} /> 删除该招聘
          </Button>
        </div>
      )}

      <ApplyDialog
        job={job}
        open={applyOpen}
        onClose={() => setApplyOpen(false)}
        onSubmitted={reload}
      />

      <ConfirmDialog
        open={closeOpen}
        title="关闭招聘"
        description={`关闭后「${job.title}」将不再接受新申请，已有申请的处理不受影响。`}
        confirmText="确认关闭"
        danger={false}
        loading={busy}
        onConfirm={doClose}
        onCancel={() => setCloseOpen(false)}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="删除招聘"
        description={
          <div className="flex flex-col gap-2">
            <p>删除操作不可逆，请确认。删除后将一并删除该招聘下的全部申请记录。</p>
            {(affected.pending > 0 || affected.accepted > 0) && (
              <p className="font-medium text-danger">
                影响范围：{affected.pending > 0 && `${affected.pending} 条处理中申请`}
                {affected.pending > 0 && affected.accepted > 0 && '、'}
                {affected.accepted > 0 && `${affected.accepted} 条已接受申请`}
              </p>
            )}
          </div>
        }
        confirmText="确认删除"
        loading={busy}
        onConfirm={doDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      <Modal
        open={moderateOpen}
        title="删除不合规内容"
        onClose={() => setModerateOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModerateOpen(false)}>
              取消
            </Button>
            <Button variant="danger" onClick={doModerate} loading={busy}>
              确认删除
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink2">
            你正在删除「{job.title}」。该操作会通知发布者并记入审计日志，请填写删除原因（至少 10 字）。
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

function InfoItem({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="flex items-center gap-1 text-xs text-ink2">
        {icon} {label}
      </span>
      <span className="text-sm font-medium text-ink">{value}</span>
    </div>
  );
}
