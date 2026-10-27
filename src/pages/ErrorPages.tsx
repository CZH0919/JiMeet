import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/Button';

export function ForbiddenPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4">
      <p className="text-6xl font-bold text-primary">403</p>
      <p className="text-lg text-ink">无权访问</p>
      <p className="max-w-sm text-center text-sm text-ink2">
        你没有权限执行该操作。若你认为这是误判，请返回首页或联系管理员。
      </p>
      <Link to="/">
        <Button>返回首页</Button>
      </Link>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4">
      <p className="text-6xl font-bold text-primary">404</p>
      <p className="text-lg text-ink">页面不存在</p>
      <p className="text-sm text-ink2">你访问的页面不存在或已被移除。</p>
      <Link to="/">
        <Button>返回首页</Button>
      </Link>
    </div>
  );
}
