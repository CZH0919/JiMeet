import { clsx } from 'clsx';

interface QuotaProgressProps {
  accepted: number;
  total: number;
}

/** 「已接受 2 / 计划 3」进度条，满员变绿 */
export function QuotaProgress({ accepted, total }: QuotaProgressProps) {
  const pct = total > 0 ? Math.min(100, (accepted / total) * 100) : 0;
  const full = accepted >= total;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-page">
        <div
          className={clsx('h-full rounded-full transition-all', full ? 'bg-success' : 'bg-primary')}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-ink2">
        已接受 <span className={clsx('font-medium', full ? 'text-success' : 'text-ink')}>{accepted}</span>{' '}
        / 计划 {total}
      </span>
    </div>
  );
}
