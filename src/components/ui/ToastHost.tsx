import { clsx } from 'clsx';
import { CheckCircle2, Info, XCircle } from 'lucide-react';
import { useToast } from '@/stores/toast';

const kindIcon = {
  success: <CheckCircle2 size={18} className="text-success" />,
  error: <XCircle size={18} className="text-danger" />,
  info: <Info size={18} className="text-primary" />,
};

export function ToastHost() {
  const toasts = useToast((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={clsx(
            'pointer-events-auto flex items-start gap-2.5 rounded-md bg-surface p-3.5 shadow-pop',
            'border-l-4',
            t.kind === 'success' && 'border-success',
            t.kind === 'error' && 'border-danger',
            t.kind === 'info' && 'border-primary',
          )}
        >
          <span className="mt-px shrink-0">{kindIcon[t.kind]}</span>
          <span className="text-sm text-ink">{t.message}</span>
        </div>
      ))}
    </div>
  );
}
