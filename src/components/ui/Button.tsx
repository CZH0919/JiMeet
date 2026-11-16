import { clsx } from 'clsx';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'danger-outline';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children?: ReactNode;
}

const variants: Record<Variant, string> = {
  primary:
    'bg-primary text-white shadow-[0_10px_24px_-14px_rgba(47,107,255,0.95)] hover:bg-primary-hover disabled:bg-muted disabled:shadow-none disabled:cursor-not-allowed',
  secondary:
    'bg-surface text-ink border border-line hover:border-primary/40 hover:text-primary disabled:text-muted disabled:cursor-not-allowed',
  danger: 'bg-danger text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed',
  'danger-outline':
    'bg-surface text-danger border border-danger/35 hover:bg-danger-soft disabled:opacity-50 disabled:cursor-not-allowed',
  ghost: 'text-ink2 hover:bg-muted-soft hover:text-ink disabled:opacity-50',
};

const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-[13px]',
  md: 'h-10 px-5 text-sm',
  lg: 'h-11 px-6 text-[15px]',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-all duration-150',
        'focus:outline-none focus-visible:ring-4 focus-visible:ring-primary/15',
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}
