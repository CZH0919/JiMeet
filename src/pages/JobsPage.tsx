import { Search, SlidersHorizontal } from 'lucide-react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { clsx } from 'clsx';
import type { JobType } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { JobCard } from '@/components/job/JobCard';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';
import { Button } from '@/components/ui/Button';

const TYPE_OPTIONS: { key: 'all' | JobType; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'competition', label: '竞赛组队' },
  { key: 'activity', label: '活动招聘' },
  { key: 'internship', label: '实验室实习' },
  { key: 'competition_notice', label: '竞赛通知' },
];

export function JobsPage() {
  const [type, setType] = useState<'all' | JobType>('all');
  const [tagId, setTagId] = useState<number | undefined>(undefined);
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 9;

  const tags = useAsync(() => repo.jobs.listTags(), []);

  const { data, loading, error, reload } = useAsync(
    () => repo.jobs.list({ type, keyword, tagId, page, pageSize }),
    [type, tagId, keyword, page],
  );

  const reset = () => {
    setType('all');
    setTagId(undefined);
    setKeyword('');
    setPage(1);
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold text-ink">招聘搜索与筛选</h1>
        <div className="relative w-full sm:w-80">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
            placeholder="搜索标题或描述关键词"
            className="w-full rounded-md border border-line bg-surface py-2 pl-9 pr-3 text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
          />
        </div>
      </div>

      <div className="flex flex-col gap-6 md:flex-row">
        <aside className="w-full shrink-0 md:w-56">
          <div className="sticky top-20 rounded-lg border border-line bg-surface p-4">
            <p className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-ink">
              <SlidersHorizontal size={15} /> 筛选
            </p>

            <FilterSection title="类型">
              {TYPE_OPTIONS.map((t) => (
                <FilterOption
                  key={t.key}
                  active={type === t.key}
                  onClick={() => {
                    setType(t.key);
                    setPage(1);
                  }}
                  label={t.label}
                />
              ))}
            </FilterSection>

            <FilterSection title="标签">
              <select
                value={tagId ?? ''}
                onChange={(e) => {
                  setTagId(e.target.value ? Number(e.target.value) : undefined);
                  setPage(1);
                }}
                className="w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:border-primary"
              >
                <option value="">全部标签</option>
                {(tags.data ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </FilterSection>

            <div className="mt-4">
              <Button size="sm" variant="secondary" className="w-full" onClick={reset}>
                重置
              </Button>
            </div>
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          <div className="mb-4 text-sm text-ink2">
            筛选结果{data ? ` · 共 ${data.total} 条` : ''}
          </div>
          {loading ? (
            <PageLoader />
          ) : error ? (
            <ErrorState message={error} onRetry={reload} />
          ) : data && data.items.length === 0 ? (
            <EmptyState title="暂无符合条件的招聘" />
          ) : (
            <>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                {data?.items.map((job) => (
                  <JobCard key={job.id} job={job} />
                ))}
              </div>
              <Pagination page={page} pageSize={pageSize} total={data?.total ?? 0} onChange={setPage} />
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function FilterSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-4">
      <p className="mb-1.5 text-xs font-medium text-ink2">{title}</p>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

function FilterOption({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'rounded px-2.5 py-1.5 text-left text-sm transition-colors',
        active ? 'bg-primary-soft font-medium text-primary' : 'text-ink2 hover:bg-page hover:text-ink',
      )}
    >
      {label}
    </button>
  );
}
