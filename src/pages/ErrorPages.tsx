import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/Button';

export function ForbiddenPage() {
  return (
    <div className="page-shell flex min-h-[60vh] flex-col items-center justify-center gap-4 py-16">
      <p className="text-6xl font-bold tracking-tight text-primary">403</p>
      <p className="text-lg font-medium text-ink">无权访问</p>
      <p className="max-w-sm text-center text-sm leading-relaxed text-ink2">
        当前账号无权访问该页面。
      </p>
      <Link to="/">
        <Button>返回首页</Button>
      </Link>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <div className="page-shell flex min-h-[60vh] flex-col items-center justify-center gap-4 py-16">
      <p className="text-6xl font-bold tracking-tight text-primary">404</p>
      <p className="text-lg font-medium text-ink">页面不存在</p>
      <p className="text-sm text-ink2">页面不存在或已被移除。</p>
      <Link to="/">
        <Button>返回首页</Button>
      </Link>
    </div>
  );
}
