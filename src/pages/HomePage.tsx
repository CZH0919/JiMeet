import { FileText, Megaphone, PenLine } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useAuth } from '@/features/useAuth';
import { formatDateTime } from '@/domain/format';
import { TIME_KIND_LABEL } from '@/domain/labels';
import { Button } from '@/components/ui/Button';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';

const PAGE_SIZE = 6;

/**
 * 首页 = 通知公告。
 * 公告与「招聘」不同类：由管理员发布竞赛/活动信息，按发布时间倒序展示（UI 稿首页）。
 */
export function HomePage() {
  const { user, ready } = useAuth();
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useAsync(
    () => (user ? repo.announcements.list({ page, pageSize: PAGE_SIZE }) : Promise.resolve(null)),
    [page, user?.id],
  );

  return (
    <div className="page-shell py-8 sm:py-10">
      <section className="panel px-6 py-7 sm:px-9 sm:py-9">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-[26px] font-bold leading-tight tracking-tight text-ink sm:text-[30px]">
              通知公告
            </h1>
            <p className="mt-2 text-sm text-ink2">按发布时间由近到远排序，最新通知优先展示</p>
          </div>
          {user?.isAdmin && (
            <Link to="/announcements/new">
              <Button size="sm" className="whitespace-nowrap">
                <PenLine size={15} /> 发布公告
              </Button>
            </Link>
          )}
        </div>

        <div className="mt-6 border-t border-line" />

        {!ready ? (
          <PageLoader />
        ) : !user ? (
          <EmptyState
            icon={<Megaphone className="h-7 w-7" />}
            title="登录后查看竞赛与活动公告"
            description="公告由管理员发布，登录后可查看详情。"
            action={
              <Link to="/login">
                <Button size="sm">去登录</Button>
              </Link>
            }
          />
        ) : loading ? (
          <PageLoader text="正在加载公告…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            icon={<Megaphone className="h-7 w-7" />}
            title="暂无公告"
            description="发布公告后会显示在这里。"
          />
        ) : (
          <>
            <ul className="flex flex-col gap-3 pt-5">
              {data.items.map((a) => (
                <li key={a.id}>
                  <Link
                    to={`/announcements/${a.id}`}
                    className="list-row group flex items-center gap-4 px-5 py-5"
                  >
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
                      <FileText size={20} strokeWidth={1.8} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-medium text-ink transition-colors group-hover:text-primary">
                        {a.title}
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink2">
                        <span>
                          {TIME_KIND_LABEL[a.timeKind]} {formatDateTime(a.eventAt)}
                        </span>
                        {a.recruitmentId && (
                          <>
                            <span className="text-muted">·</span>
                            <span>关联招聘</span>
                          </>
                        )}
                        {a.linkUrl && (
                          <>
                            <span className="text-muted">·</span>
                            <span>含相关链接</span>
                          </>
                        )}
                      </span>
                    </span>
                    <time className="hidden shrink-0 text-sm tabular-nums text-ink2 sm:block">
                      {formatDateTime(a.createdAt)}
                    </time>
                  </Link>
                </li>
              ))}
            </ul>

            <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
          </>
        )}
      </section>
    </div>
  );
}
