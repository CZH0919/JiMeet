import { clsx } from 'clsx';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect } from 'react';

interface ModalProps {
  open: boolean;
  title?: ReactNode;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}

export function Modal({ open, title, description, onClose, children, footer, width = 'max-w-lg' }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/35 backdrop-blur-[2px]" onClick={onClose} />
      <div className={clsx('relative w-full animate-fade-in rounded-lg bg-surface shadow-pop', width)}>
        {title && (
          <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
            <div>
              <h3 className="text-base font-semibold text-ink">{title}</h3>
              {description && <p className="mt-1 text-xs leading-relaxed text-ink2">{description}</p>}
            </div>
            <button
              onClick={onClose}
              className="-mr-1 rounded-md p-1.5 text-muted transition-colors hover:bg-muted-soft hover:text-ink"
              aria-label="关闭"
            >
              <X size={18} />
            </button>
          </div>
        )}
        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">{children}</div>
        {footer && (
          <div className="flex justify-end gap-3 border-t border-line px-6 py-4">{footer}</div>
        )}
      </div>
    </div>
  );
}
