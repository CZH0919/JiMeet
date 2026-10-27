import { clsx } from 'clsx';
import { Link } from 'react-router-dom';

export function Logo({ to = '/', small = false }: { to?: string; small?: boolean }) {
  return (
    <Link to={to} className="flex items-center gap-2">
      <span
        className={clsx(
          'flex items-center justify-center rounded-md bg-primary font-semibold text-white',
          small ? 'h-7 w-7 text-base' : 'h-9 w-9 text-xl',
        )}
      >
        济
      </span>
      <span className={clsx('font-semibold text-ink', small ? 'text-lg' : 'text-xl')}>济遇</span>
    </Link>
  );
}
