import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}

export function Pagination({ page, pageSize, total, onChange }: PaginationProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-2 py-6">
      <button
        className="flex h-8 items-center gap-0.5 rounded-md border border-line bg-surface px-3 text-sm text-ink2 hover:text-ink disabled:opacity-40"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        <ChevronLeft size={15} /> 上一页
      </button>
      <span className="px-2 text-sm text-ink2">
        {page} / {pages}
      </span>
      <button
        className="flex h-8 items-center gap-0.5 rounded-md border border-line bg-surface px-3 text-sm text-ink2 hover:text-ink disabled:opacity-40"
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
      >
        下一页 <ChevronRight size={15} />
      </button>
    </div>
  );
}
