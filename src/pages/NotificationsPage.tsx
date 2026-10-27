import { Bell } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { clsx } from 'clsx';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { formatDateTime } from '@/domain/jobStatus';
import { NOTIFICATION_TYPE_LABEL } from '@/domain/labels';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';
import { Button } from '@/components/ui/Button';
import { toast } from '@/stores/toast';

export function NotificationsPage() {
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const { data, loading, error, reload } = useAsync(
    () => repo.notifications.list({ page, pageSize }),
    [page],
  );

  const markAll = async () => {
    await repo.notifications.markAllRead();
    toast.success('已全部标记为已读');
    reload();
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-ink">
          <Bell size={20} /> 站内通知中心
        </h1>
        <Button variant="secondary" size="sm" onClick={markAll}>
          全部标记已读
        </Button>
      </div>

      {loading ? (
        <PageLoader />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data && data.items.length === 0 ? (
        <EmptyState title="暂无通知" />
      ) : (
        <div className="flex flex-col gap-3">
          {data?.items.map((n) => {
            // 招聘已被删除时详情页必定 404，这类通知不跳转，只标记已读
            const canOpenJob = Boolean(n.jobId) && n.type !== 'job_removed_by_admin';
            const className = clsx(
              'block w-full rounded-lg border bg-surface p-4 text-left transition-colors',
              canOpenJob && 'hover:border-primary',
              n.read ? 'border-line' : 'border-primary/40 bg-primary-soft/30',
            );
            const markRead = () => {
              if (!n.read) repo.notifications.markRead(n.id).then(reload);
            };
            const content = (
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-ink">{NOTIFICATION_TYPE_LABEL[n.type]}</span>
                    {!n.read ? (
                      <span className="shrink-0 rounded-full bg-danger-soft px-2 py-0.5 text-xs text-danger">未读</span>
                    ) : (
                      <span className="shrink-0 rounded-full bg-muted-soft px-2 py-0.5 text-xs text-muted">已读</span>
                    )}
                  </div>
                  <p className="mt-1 break-words text-sm leading-relaxed text-ink2">{n.title}</p>
                  {n.body && (
                    <p className="mt-1 whitespace-pre-line break-words text-sm leading-relaxed text-ink2">{n.body}</p>
                  )}
                  {n.jobTitle && (
                    <p className="mt-1 truncate text-xs text-muted">相关招聘：{n.jobTitle}</p>
                  )}
                  <p className="mt-1 text-xs text-muted">{formatDateTime(n.createdAt)}</p>
                </div>
              </div>
            );

            return canOpenJob ? (
              <Link
                key={n.id}
                to={`/jobs/${n.jobId}`}
                onClick={markRead}
                className={className}
              >
                {content}
              </Link>
            ) : (
              <button key={n.id} type="button" onClick={markRead} className={className}>
                {content}
              </button>
            );
          })}
          <Pagination page={page} pageSize={pageSize} total={data?.total ?? 0} onChange={setPage} />
        </div>
      )}
    </div>
  );
}
