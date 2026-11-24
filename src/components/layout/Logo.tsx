import { Link } from 'react-router-dom';
import { clsx } from 'clsx';

/** 品牌标识：站点 logo（public/logo.png）+ 文字标 + 平台说明 */
export function Logo({ to = '/', compact = false }: { to?: string; compact?: boolean }) {
  return (
    <Link to={to} className="flex shrink-0 items-center gap-2 sm:gap-2.5" aria-label="济遇 首页">
      <img
        src="/logo.png"
        alt=""
        className={clsx('w-auto shrink-0 select-none object-contain', compact ? 'h-8' : 'h-8 sm:h-11')}
        draggable={false}
      />
      <span
        className={clsx(
          'font-bold tracking-tight text-ink',
          compact ? 'text-xl' : 'text-lg sm:text-[22px]',
        )}
      >
        济遇
      </span>
      <span className="hidden h-5 w-px bg-line md:block" />
      <span className="hidden whitespace-nowrap text-[13px] text-ink2 md:block">
        校内竞赛 &amp; 活动招聘平台
      </span>
    </Link>
  );
}
