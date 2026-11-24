import { ChevronLeft, ChevronRight } from 'lucide-react';
import { clsx } from 'clsx';

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}

/** 生成页码序列，页数过多时用省略号折叠 */
function pageItems(page: number, pages: number): (number | 'gap')[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const items: (number | 'gap')[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(pages - 1, page + 1);
  if (start > 2) items.push('gap');
  for (let i = start; i <= end; i += 1) items.push(i);
  if (end < pages - 1) items.push('gap');
  items.push(pages);
  return items;
}

export function Pagination({ page, pageSize, total, onChange }: PaginationProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;

  const btn =
    'flex h-9 min-w-9 items-center justify-center rounded-md border border-line bg-surface px-3 text-sm text-ink2 transition-colors hover:border-primary/40 hover:text-primary disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-line disabled:hover:text-ink2';

  return (
    <nav className="mt-8 flex flex-wrap items-center justify-center gap-2" aria-label="分页">
      <button className={btn} disabled={page <= 1} onClick={() => onChange(page - 1)}>
        <ChevronLeft size={15} /> 上一页
      </button>

      {pageItems(page, pages).map((item, idx) =>
        item === 'gap' ? (
          <span key={`gap-${idx}`} className="px-1 text-sm text-muted">
            …
          </span>
        ) : (
          <button
            key={item}
            aria-current={item === page ? 'page' : undefined}
            onClick={() => onChange(item)}
            className={clsx(
              'flex h-9 min-w-9 items-center justify-center rounded-md border px-2 text-sm transition-colors',
              item === page
                ? 'border-primary bg-primary font-medium text-white'
                : 'border-line bg-surface text-ink2 hover:border-primary/40 hover:text-primary',
            )}
          >
            {item}
          </button>
        ),
      )}

      <button className={btn} disabled={page >= pages} onClick={() => onChange(page + 1)}>
        下一页 <ChevronRight size={15} />
      </button>
    </nav>
  );
}
