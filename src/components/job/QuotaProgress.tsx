import { clsx } from 'clsx';

interface QuotaProgressProps {
  accepted: number;
  total: number;
  showLabel?: boolean;
}

/** 已接受人数 / 计划招募人数进度条 */
export function QuotaProgress({ accepted, total, showLabel = true }: QuotaProgressProps) {
  const safeTotal = Math.max(total, 0);
  const ratio = safeTotal > 0 ? Math.min(1, accepted / safeTotal) : 0;
  const full = safeTotal > 0 && accepted >= safeTotal;

  return (
    <div className="flex flex-col gap-1.5">
      {showLabel && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-ink2">已接受</span>
          <span className={clsx('font-medium', full ? 'text-warning' : 'text-ink')}>
            {accepted} / {safeTotal || '—'}
          </span>
        </div>
      )}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted-soft">
        <div
          className={clsx('h-full rounded-full transition-all', full ? 'bg-warning' : 'bg-primary')}
          style={{ width: `${Math.round(ratio * 100)}%` }}
        />
      </div>
    </div>
  );
}
