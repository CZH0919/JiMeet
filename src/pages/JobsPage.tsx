import { RotateCcw, Search } from 'lucide-react';
import { clsx } from 'clsx';
import type { JobStatus, JobType } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from '@/features/useAsync';
import { useJobList } from '@/features/useJobs';
import { JOB_STATUS_LABEL } from '@/domain/labels';
import { JobCard } from '@/components/job/JobCard';
import { EmptyState, ErrorState, PageLoader } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';

const TYPE_OPTIONS: { key: 'all' | JobType; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'competition', label: '竞赛组队' },
  { key: 'activity', label: '活动招聘' },
  { key: 'internship', label: '实验室实习' },
];

const STATUS_OPTIONS: { key: 'all' | JobStatus; label: string }[] = [
  { key: 'all', label: '全部状态' },
  { key: 'open', label: JOB_STATUS_LABEL.open },
  { key: 'full', label: JOB_STATUS_LABEL.full },
  { key: 'closed', label: JOB_STATUS_LABEL.closed },
];

export function JobsPage() {
  const {
    type,
    setType,
    keyword,
    setKeyword,
    tagId,
    setTagId,
    status,
    setStatus,
    page,
    setPage,
    pageSize,
    data,
    loading,
    error,
    reload,
  } = useJobList('all', 9);

  const tags = useAsync(() => repo.jobs.listTags(), []);

  const reset = () => {
    setType('all');
    setTagId(undefined);
    setStatus(undefined);
    setKeyword('');
    setPage(1);
  };

  return (
    <div className="page-shell py-8 sm:py-10">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-[26px] font-bold tracking-tight text-ink">招聘</h1>
          <p className="mt-2 text-sm text-ink2">竞赛组队、校内活动与实验室实习</p>
        </div>
        <div className="relative w-full sm:w-80">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
            placeholder="搜索标题或需求描述"
            className="w-full rounded-full border border-line bg-surface py-2.5 pl-10 pr-4 text-sm text-ink transition-colors placeholder:text-muted focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/10"
          />
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="panel mt-6 flex flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-1">
          {TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => {
                setType(opt.key);
                setPage(1);
              }}
              className={clsx(
                'rounded-full px-4 py-1.5 text-sm transition-colors',
                type === opt.key
                  ? 'bg-primary-soft font-medium text-primary'
                  : 'text-ink2 hover:bg-muted-soft hover:text-ink',
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={tagId ?? ''}
            onChange={(e) => {
              setTagId(e.target.value ? Number(e.target.value) : undefined);
              setPage(1);
            }}
            className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink2 focus:border-primary focus:outline-none"
          >
            <option value="">全部标签</option>
            {(tags.data ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>

          <select
            value={status ?? 'all'}
            onChange={(e) => {
              setStatus(e.target.value === 'all' ? undefined : (e.target.value as JobStatus));
              setPage(1);
            }}
            className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink2 focus:border-primary focus:outline-none"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>

          <button
            onClick={reset}
            className="inline-flex h-9 items-center gap-1 rounded-md px-3 text-sm text-ink2 transition-colors hover:bg-muted-soft hover:text-ink"
          >
            <RotateCcw size={14} /> 重置
          </button>
        </div>
      </div>

      <div className="mt-5 flex items-center justify-between">
        <p className="text-sm text-ink2">{data ? `共 ${data.total} 条招聘` : '加载中…'}</p>
      </div>

      <div className="mt-4">
        {loading ? (
          <PageLoader text="正在加载招聘…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState title="暂无符合条件的招聘" description="调整筛选条件后重试" />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {data.items.map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
            </div>
            <Pagination page={page} pageSize={pageSize} total={data.total} onChange={setPage} />
          </>
        )}
      </div>
    </div>
  );
}
