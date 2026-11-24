import { ArrowLeft, ExternalLink, Megaphone, PenLine, ShieldAlert, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { formatDateTime } from '@/domain/format';
import { ROLE_LABEL, TIME_KIND_LABEL } from '@/domain/labels';
import { can } from '@/domain/permissions';
import { validateModerationReason } from '@/domain/validation';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Field, Textarea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { toast } from '@/stores/toast';

export function AnnouncementDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: item, loading, error, reload } = useAsync(
    () => repo.announcements.detail(id!),
    [id],
  );

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [governOpen, setGovernOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [reasonErr, setReasonErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <PageLoader />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!item) return null;

  const doDeleteOwn = async () => {
    setBusy(true);
    try {
      await repo.announcements.removeOwn(item.id);
      toast.success('公告已删除');
      navigate('/', { replace: true });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '删除失败');
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
      await repo.announcements.governRemove(item.id, reason);
      toast.success('已下架该公告并通知作者');
      navigate('/', { replace: true });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-shell max-w-[900px] py-8 sm:py-10">
      <Link
        to="/"
        className="mb-4 inline-flex items-center gap-1 text-sm text-ink2 transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} /> 返回公告列表
      </Link>

      <article className="panel px-6 py-7 sm:px-9 sm:py-9">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <span className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
              <Megaphone size={20} strokeWidth={1.8} />
            </span>
            <div className="min-w-0">
              <h1 className="text-2xl font-bold leading-snug tracking-tight text-ink">{item.title}</h1>
              <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink2">
                <span>
                  {TIME_KIND_LABEL[item.timeKind]}：{formatDateTime(item.eventAt)}
                </span>
                <span className="text-muted">·</span>
                <span>
                  发布者 {item.author.name}（{ROLE_LABEL[item.author.role]}）
                </span>
                <span className="text-muted">·</span>
                <span>发布于 {formatDateTime(item.createdAt)}</span>
              </p>
            </div>
          </div>

          {user?.isAdmin && can.editAnnouncement(user, item) && (
            <div className="flex shrink-0 items-center gap-2">
              <Link to={`/announcements/${item.id}/edit`}>
                <Button size="sm" variant="secondary">
                  <PenLine size={14} /> 编辑
                </Button>
              </Link>
              <Button size="sm" variant="danger-outline" onClick={() => setDeleteOpen(true)}>
                <Trash2 size={14} /> 删除
              </Button>
            </div>
          )}
        </div>

        <div className="mt-6 border-t border-line pt-6">
          <p className="whitespace-pre-wrap text-[15px] leading-8 text-ink2">{item.content}</p>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          {item.linkUrl && (
            <a
              href={item.linkUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line bg-surface px-4 text-sm text-primary transition-colors hover:border-primary/40"
            >
              <ExternalLink size={15} /> 查看相关链接
            </a>
          )}
          {item.recruitmentId &&
            (item.recruitmentAvailable ? (
              <Link
                to={`/jobs/${item.recruitmentId}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line bg-surface px-4 text-sm text-ink transition-colors hover:border-primary/40 hover:text-primary"
              >
                查看关联招聘
              </Link>
            ) : (
              <span className="text-xs text-muted">关联招聘已删除或不可见</span>
            ))}
        </div>
      </article>

      {/* 管理员治理区：与作者本人操作分开（SRS 2.3 / FR-11） */}
      {user?.isAdmin && can.governDeleteAnnouncement(item) && (
        <section className="mt-5 rounded-lg border border-danger/25 bg-danger-soft/40 px-6 py-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-danger">
            <ShieldAlert size={16} /> 内容治理
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-ink2">
            需填写原因，操作将记入审计日志并通知作者。
          </p>
          <Button variant="danger" size="sm" className="mt-3" onClick={() => setGovernOpen(true)}>
            <Trash2 size={14} /> 下架该公告
          </Button>
        </section>
      )}

      <ConfirmDialog
        open={deleteOpen}
        title="删除公告"
        description={`确认删除「${item.title}」？删除后公告从列表移除，不可恢复。`}
        confirmText="确认删除"
        loading={busy}
        onConfirm={doDeleteOwn}
        onCancel={() => setDeleteOpen(false)}
      />

      <Modal
        open={governOpen}
        title="治理下架公告"
        onClose={() => setGovernOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setGovernOpen(false)}>
              取消
            </Button>
            <Button variant="danger" onClick={doGovern} loading={busy}>
              确认下架
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm leading-relaxed text-ink2">
            下架「{item.title}」并通知作者，原因将写入审计日志。
          </p>
          <Field error={reasonErr ?? undefined} hint="1～500 字">
            <Textarea
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                setReasonErr(null);
              }}
              placeholder="请填写下架原因"
              maxLength={500}
            />
          </Field>
        </div>
      </Modal>
    </div>
  );
}
