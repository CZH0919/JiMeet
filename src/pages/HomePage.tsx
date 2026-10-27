import { Search } from 'lucide-react';
import { useJobList } from '@/features/useJobs';
import type { TypeFilter } from '@/features/useJobs';
import { JobCard } from '@/components/job/JobCard';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';
import { clsx } from 'clsx';

const TABS: { key: TypeFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'competition', label: '竞赛组队' },
  { key: 'campus_activity', label: '活动招聘' },
];

export function HomePage() {
  const { type, setType, keyword, setKeyword, sort, setSort, page, setPage, pageSize, data, loading, error, reload } =
    useJobList('all', 9);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-col items-start justify-between gap-4 rounded-xl bg-gradient-to-r from-[#EAF3FC] to-white p-6 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-semibold text-ink">招聘信息</h1>
          <p className="mt-1 text-sm text-ink2">根据你的偏好个性化推送招聘，发现合适的竞赛与活动机会</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-ink2">
          <span>按时间与推荐度排序</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as 'latest' | 'earliest')}
            className="rounded-md border border-line bg-surface px-2 py-1 text-sm focus:outline-none focus:border-primary"
          >
            <option value="latest">最新发布</option>
            <option value="earliest">最早发布</option>
          </select>
        </div>
      </div>

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-1 rounded-md bg-page p-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => {
                setType(t.key);
                setPage(1);
              }}
              className={clsx(
                'rounded px-4 py-1.5 text-sm font-medium transition-colors',
                type === t.key ? 'bg-surface text-primary shadow-card' : 'text-ink2 hover:text-ink',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-72">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
            placeholder="搜索竞赛、活动、项目关键词"
            className="w-full rounded-md border border-line bg-surface py-2 pl-9 pr-3 text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
          />
        </div>
      </div>

      {loading ? (
        <PageLoader />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : data && data.items.length === 0 ? (
        <EmptyState title="暂无符合条件的招聘" />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
            {data?.items.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
          <Pagination page={page} pageSize={pageSize} total={data?.total ?? 0} onChange={setPage} />
        </>
      )}
    </div>
  );
}
