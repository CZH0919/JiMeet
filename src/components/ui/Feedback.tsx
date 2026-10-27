import { clsx } from 'clsx';
import { CheckCircle2, Info, Inbox, XCircle } from 'lucide-react';
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
    <div className="flex flex-col items-center justify-center gap-3 py-24">
      <XCircle className="h-10 w-10 text-danger" />
      <p className="text-sm text-ink2">{message}</p>
      {onRetry && (
        <button className="text-sm font-medium text-primary hover:underline" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  );
}

export function EmptyState({ icon, title, action }: { icon?: ReactNode; title: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20">
      {icon ?? <Inbox className="h-12 w-12 text-muted" />}
      <p className="text-sm text-muted">{title}</p>
      {action}
    </div>
  );
}

export function InfoBanner({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-primary-soft px-4 py-3 text-sm text-primary">
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function SuccessMark() {
  return <CheckCircle2 className="h-12 w-12 text-success" />;
}
