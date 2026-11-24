import { clsx } from 'clsx';
import { Info, Inbox, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={clsx(
        'inline-block h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent',
        className,
      )}
    />
  );
}

export function PageLoader({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-muted">
      <Spinner className="h-8 w-8" />
      <span className="text-sm">{text}</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20">
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-danger-soft">
        <XCircle className="h-7 w-7 text-danger" />
      </span>
      <p className="max-w-sm text-center text-sm leading-relaxed text-ink2">{message}</p>
      {onRetry && (
        <button className="text-sm font-medium text-primary hover:underline" onClick={onRetry}>
          重新加载
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <span className="flex h-16 w-16 items-center justify-center rounded-full bg-muted-soft text-muted">
        {icon ?? <Inbox className="h-7 w-7" />}
      </span>
      <p className="text-sm font-medium text-ink2">{title}</p>
      {description && <p className="max-w-sm text-center text-xs leading-relaxed text-muted">{description}</p>}
      {action}
    </div>
  );
}

export function InfoBanner({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-primary-soft px-4 py-3 text-[13px] leading-relaxed text-primary">
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}
