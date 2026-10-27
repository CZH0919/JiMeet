import { Search, SlidersHorizontal } from 'lucide-react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { clsx } from 'clsx';
import type { JobType } from '@/domain/models';
import { FIELDS } from '@/domain/labels';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { JobCard } from '@/components/job/JobCard';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';
import { Button } from '@/components/ui/Button';

const RECRUIT_OPTIONS = [
  { value: 0, label: '不限' },
  { value: 2, label: '2 人以上' },
  { value: 4, label: '4 人以上' },
  { value: 7, label: '7 人以上' },
];

const DEADLINE_OPTIONS = [
  { value: 0, label: '不限' },
  { value: 7, label: '近 7 天' },
  { value: 30, label: '近 30 天' },
];

export function JobsPage() {
  const [type, setType] = useState<'all' | JobType>('all');
  const [field, setField] = useState('all');
  const [minRecruit, setMinRecruit] = useState(0);
  const [deadlineWithin, setDeadlineWithin] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [sort, setSort] = useState<'latest' | 'earliest'>('latest');
  const [page, setPage] = useState(1);
  const pageSize = 9;

  const { data, loading, error, reload } = useAsync(
    () =>
      repo.jobs.list({
        type,
        field,
        minRecruit: minRecruit || undefined,
        deadlineWithin: deadlineWithin || undefined,
        keyword,
        sort,
        page,
        pageSize,
      }),
    [type, field, minRecruit, deadlineWithin, keyword, sort, page],
  );

  const reset = () => {
    setType('all');
    setField('all');
    setMinRecruit(0);
    setDeadlineWithin(0);
    setKeyword('');
    setPage(1);
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold text-ink">招聘搜索与筛选</h1>
        <div className="flex items-center gap-3">
          <div className="relative w-full sm:w-80">
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
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as 'latest' | 'earliest')}
            className="rounded-md border border-line bg-surface px-3 py-2 text-sm focus:outline-none focus:border-primary"
          >
            <option value="latest">最新</option>
            <option value="earliest">最早</option>
          </select>
        </div>
      </div>

      <div className="flex flex-col gap-6 md:flex-row">
        <aside className="w-full shrink-0 md:w-56">
          <div className="sticky top-20 rounded-lg border border-line bg-surface p-4">
            <p className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-ink">
              <SlidersHorizontal size={15} /> 筛选
            </p>

            <FilterSection title="类型">
              {(['all', 'competition', 'campus_activity'] as const).map((t) => (
                <FilterOption
                  key={t}
                  active={type === t}
                  onClick={() => {
                    setType(t);
                    setPage(1);
                  }}
                  label={t === 'all' ? '全部' : t === 'competition' ? '竞赛组队' : '活动招聘'}
                />
              ))}
            </FilterSection>

            <FilterSection title="相关领域">
              <FilterOption active={field === 'all'} onClick={() => setField('all')} label="全部" />
              {FIELDS.map((f) => (
                <FilterOption
                  key={f}
                  active={field === f}
                  onClick={() => {
                    setField(f);
                    setPage(1);
                  }}
                  label={f}
                />
              ))}
            </FilterSection>

            <FilterSection title="招募人数">
              {RECRUIT_OPTIONS.map((o) => (
                <FilterOption
                  key={o.value}
                  active={minRecruit === o.value}
                  onClick={() => {
                    setMinRecruit(o.value);
                    setPage(1);
                  }}
                  label={o.label}
                />
              ))}
            </FilterSection>

            <FilterSection title="截止时间">
              {DEADLINE_OPTIONS.map((o) => (
                <FilterOption
                  key={o.value}
                  active={deadlineWithin === o.value}
                  onClick={() => {
                    setDeadlineWithin(o.value);
                    setPage(1);
                  }}
                  label={o.label}
                />
              ))}
            </FilterSection>

            <div className="mt-4 flex gap-2">
              <Button size="sm" variant="primary" className="flex-1">
                筛选
              </Button>
              <Button size="sm" variant="secondary" className="flex-1" onClick={reset}>
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
