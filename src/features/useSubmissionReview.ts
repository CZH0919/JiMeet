import { useCallback, useEffect, useState } from 'react';
import { repo } from '@/data';
import { useSession } from '@/stores/session';

/**
 * 管理员待审投稿数：用于「公告审核工作台」红点。
 * 非管理员不请求该接口，避免无意义的 403。
 */
export function usePendingSubmissionCount() {
  const user = useSession((s) => s.user);
  const isAdmin = user?.isAdmin === true;
  const [count, setCount] = useState(0);

  const refresh = useCallback(async () => {
    if (!isAdmin) {
      setCount(0);
      return;
    }
    try {
      setCount(await repo.announcements.pendingSubmissionCount());
    } catch {
      /* 轮询失败不打扰用户，保留上次数值 */
    }
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin) {
      setCount(0);
      return;
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(timer);
  }, [isAdmin, refresh]);

  return { count, refresh };
}
