import { clsx } from 'clsx';
import { CheckCircle2, Info, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import type { ToastKind } from '@/stores/toast';
import { useToast } from '@/stores/toast';

const TONE: Record<ToastKind, { wrap: string; icon: ReactNode }> = {
  success: { wrap: 'bg-success-soft text-success', icon: <CheckCircle2 size={16} /> },
  error: { wrap: 'bg-danger-soft text-danger', icon: <XCircle size={16} /> },
  info: { wrap: 'bg-primary-soft text-primary', icon: <Info size={16} /> },
};

/** 轻量提示：页面顶部居中的浮层，图标着色，避免遮挡页头与操作按钮 */
export function ToastHost() {
  const toasts = useToast((s) => s.toasts);

  return (
    <div
      className="pointer-events-none fixed left-1/2 top-[84px] z-[100] flex w-full max-w-md -translate-x-1/2 flex-col items-center gap-2 px-4"
      aria-live="polite"
      role="status"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className="pointer-events-auto flex max-w-full animate-toast-in items-start gap-2.5 rounded-lg border border-line/70 bg-surface/95 px-3.5 py-3 shadow-pop backdrop-blur"
        >
          <span
            className={clsx(
              'mt-px flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
              TONE[t.kind].wrap,
            )}
          >
            {TONE[t.kind].icon}
          </span>
          <span className="min-w-0 flex-1 pt-0.5 text-[13px] leading-relaxed text-ink">{t.message}</span>
        </div>
      ))}
    </div>
  );
}
