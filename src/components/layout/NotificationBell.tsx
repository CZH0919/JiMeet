import { Bell, CheckCheck, CheckCircle2, FileText, ShieldAlert, Users, X, XCircle } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { clsx } from 'clsx';
import type { Notification, NotificationType } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { formatRelative } from '@/domain/format';
import { NOTIFICATION_TYPE_LABEL } from '@/domain/labels';
import { useSession } from '@/stores/session';
import { toast } from '@/stores/toast';

interface Props {
  unread: number;
  /** 已读/全部已读后刷新未读数 */
  onRead: () => void;
}

function iconOf(type: NotificationType) {
  switch (type) {
    case 'application_accepted':
    case 'announcement_submission_approved':
      return { Icon: CheckCircle2, tone: 'bg-success-soft text-success' };
    case 'application_rejected':
    case 'announcement_submission_rejected':
      return { Icon: XCircle, tone: 'bg-danger-soft text-danger' };
    case 'announcement_admin_removed':
    case 'announcement_removed':
    case 'admin_removed':
    case 'recruitment_deleted':
      return { Icon: ShieldAlert, tone: 'bg-danger-soft text-danger' };
    case 'recruitment_closed':
    case 'recruitment_updated':
      return { Icon: Users, tone: 'bg-primary-soft text-primary' };
    default:
      return { Icon: FileText, tone: 'bg-primary-soft text-primary' };
  }
}

/** 站内通知的跳转目标：目标已删除时不跳转，只提示 */
function targetOf(n: Notification): string | null {
  if (n.type === 'announcement_submission_rejected') return '/me?tab=submissions';
  if (n.announcementId) return `/announcements/${n.announcementId}`;

  // 发布者侧的申请事件去「收到的申请」，申请人侧的结果去「我提交的申请」
  const publisherSide =
    n.type === 'application_submitted' ||
    n.type === 'application_updated' ||
    n.type === 'application_withdrawn' ||
    n.type === 'anonymous_withdrawal' ||
    n.type === 'recruitment_closed' ||
    n.type === 'recruitment_deleted';
  if (publisherSide) return '/me?tab=received';
  if (n.applicationId) return '/me?tab=applications';
  if (n.jobId) return `/jobs/${n.jobId}`;
  return null;
}

/**
 * 站内通知小喇叭：位于用户头像左侧，点击后从页面右侧展开通知面板。
 * 通知分页页已按 UI 稿移除，此面板即通知的唯一入口。
 */
export function NotificationBell({ unread, onRead }: Props) {
  const user = useSession((s) => s.user);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const { data, loading, error, reload } = useAsync(
    () => (open && user ? repo.notifications.list({ page: 1, pageSize: 20 }) : Promise.resolve(null)),
    [open, user?.id],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  }, [open]);

  if (!user) return null;

  const openItem = async (n: Notification) => {
    const target = targetOf(n);
    if (!n.read) {
      try {
        await repo.notifications.markRead(n.id);
        onRead();
        reload();
      } catch {
        /* 已读失败不阻塞跳转 */
      }
    }
    setOpen(false);
    if (n.targetIsDeleted) {
      toast.info('该内容已被删除，相关记录仍保留在个人中心');
      return;
    }
    if (target) navigate(target);
  };

  const readAll = async () => {
    try {
      const updated = await repo.notifications.markAllRead();
      toast.success(updated > 0 ? `已将 ${updated} 条通知标为已读` : '没有未读通知');
      onRead();
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '操作失败');
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="站内通知"
        aria-expanded={open}
        className={clsx(
          'relative flex h-10 w-10 items-center justify-center rounded-full border transition-colors',
          open
            ? 'border-primary/40 bg-primary-soft text-primary'
            : 'border-line bg-surface text-ink2 hover:border-primary/30 hover:text-primary',
        )}
      >
        <Bell size={19} strokeWidth={1.9} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-none text-white ring-2 ring-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          {/* 移动端：轻遮罩，点击关闭 */}
          <div
            className="fixed inset-0 top-[72px] z-30 bg-ink/25 sm:hidden"
            onClick={() => setOpen(false)}
            aria-hidden
          />

          {/* 右侧面板：从页面右侧展开，与内容区形成平衡 */}
          <aside
            role="dialog"
            aria-label="站内通知"
            className="fixed right-0 top-[72px] z-40 flex h-[calc(100vh-72px)] w-full animate-slide-in flex-col border-l border-line bg-surface shadow-pop sm:w-[400px]"
          >
            <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-ink">站内通知</span>
                {unread > 0 && (
                  <span className="rounded-full bg-danger-soft px-2 py-0.5 text-[11px] font-medium text-danger">
                    {unread} 条未读
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={readAll}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-primary transition-colors hover:bg-primary-soft"
                >
                  <CheckCheck size={14} /> 全部已读
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="关闭通知"
                  className="rounded-md p-1.5 text-muted transition-colors hover:bg-muted-soft hover:text-ink"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {loading ? (
                <p className="py-16 text-center text-sm text-muted">加载中…</p>
              ) : error ? (
                <div className="px-6 py-12 text-center">
                  <p className="text-sm text-ink2">{error}</p>
                  <button onClick={reload} className="mt-2 text-sm font-medium text-primary hover:underline">
                    重试
                  </button>
                </div>
              ) : !data || data.items.length === 0 ? (
                <div className="flex flex-col items-center gap-2 px-6 py-16 text-center">
                  <span className="flex h-12 w-12 items-center justify-center rounded-full bg-muted-soft text-muted">
                    <Bell size={20} />
                  </span>
                  <p className="text-sm text-ink2">暂无通知</p>
                </div>
              ) : (
                <ul>
                  {data.items.map((n) => {
                    const { Icon, tone } = iconOf(n.type);
                    return (
                      <li key={n.id}>
                        <button
                          type="button"
                          onClick={() => void openItem(n)}
                          className={clsx(
                            'flex w-full items-start gap-3 border-b border-line/70 px-5 py-4 text-left transition-colors hover:bg-page',
                            !n.read && 'bg-primary-soft/25',
                          )}
                        >
                          <span
                            className={clsx(
                              'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                              tone,
                            )}
                          >
                            <Icon size={16} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-2">
                              <span className="truncate text-[13px] font-semibold text-ink">{n.title}</span>
                              {!n.read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-danger" />}
                            </span>
                            {n.body && (
                              <span className="mt-1 line-clamp-2 block text-xs leading-relaxed text-ink2">
                                {n.body}
                              </span>
                            )}
                            <span className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                              <span>{NOTIFICATION_TYPE_LABEL[n.type]}</span>
                              <span>·</span>
                              <span>{formatRelative(n.createdAt)}</span>
                              {n.targetIsDeleted && (
                                <span className="rounded bg-muted-soft px-1.5 py-0.5 text-[10px] text-ink2">
                                  目标已删除
                                </span>
                              )}
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <div className="border-t border-line bg-page/50 px-5 py-3 text-center text-[11px] text-muted">
              最近 20 条通知
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
