import { Bell, X } from 'lucide-react';
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { clsx } from 'clsx';
import { formatDateTime } from '@/domain/jobStatus';
import { NOTIFICATION_TYPE_LABEL } from '@/domain/labels';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useSession } from '@/stores/session';
import { EmptyState, ErrorState } from '@/components/ui/Feedback';

interface Props {
  open: boolean;
  onClose: () => void;
}

export function NotificationDrawer({ open, onClose }: Props) {
  const user = useSession((s) => s.user);
  const { data, loading, error, reload } = useAsync(
    () => repo.notifications.list({ page: 1, pageSize: 10 }),
    [user, open],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  const initialLoading = loading && !data;

  // 必须挂到 body：header 带 backdrop-blur（backdrop-filter），会成为 fixed 后代的包含块，
  // 抽屉留在 header 内部会被压成 64px 高的一条，导致内容显示不全。
  return createPortal(
    <div className="fixed inset-0 z-[100]" role="dialog" aria-modal="true" aria-label="通知">
      <div className="absolute inset-0 bg-ink/30" onClick={onClose} />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-sm flex-col bg-surface shadow-pop">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="flex items-center gap-2">
            <Bell size={18} />
            <span className="text-base font-semibold text-ink">通知</span>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-page hover:text-ink" aria-label="关闭">
            <X size={18} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-3">
          {initialLoading ? (
            <div className="py-12 text-center text-sm text-muted">加载中…</div>
          ) : error ? (
            <ErrorState message={error} onRetry={reload} />
          ) : data && data.items.length === 0 ? (
            <EmptyState title="暂无通知" />
          ) : (
            <ul className="flex flex-col gap-2">
              {data?.items.map((n) => (
                <li key={n.id}>
                  <Link
                    to={n.jobId ? `/jobs/${n.jobId}` : '/notifications'}
                    onClick={() => {
                      repo.notifications.markRead(n.id).then(reload);
                      onClose();
                    }}
                    className={clsx(
                      'block rounded-md border px-4 py-3 transition-colors',
                      n.read ? 'border-line hover:bg-page' : 'border-primary/40 bg-primary-soft/30 hover:bg-page',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-ink">{NOTIFICATION_TYPE_LABEL[n.type]}</span>
                      {!n.read && <span className="h-2 w-2 shrink-0 rounded-full bg-danger" />}
                    </div>
                    <p className="mt-1 break-words text-sm leading-relaxed text-ink2">{n.title}</p>
                    {n.body && <p className="mt-1 break-words text-xs leading-relaxed text-ink2">{n.body}</p>}
                    {n.jobTitle && <p className="mt-1 truncate text-xs text-muted">相关招聘：{n.jobTitle}</p>}
                    <p className="mt-1 text-xs text-muted">{formatDateTime(n.createdAt)}</p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <Link
          to="/notifications"
          onClick={onClose}
          className="shrink-0 border-t border-line py-3 text-center text-sm text-primary hover:bg-page"
        >
          查看全部通知
        </Link>
      </aside>
    </div>,
    document.body,
  );
}
