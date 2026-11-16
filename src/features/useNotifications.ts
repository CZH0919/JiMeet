import { useCallback, useEffect, useState } from 'react';
import { repo } from '@/data';
import { useSession } from '@/stores/session';

/** 未读通知数：登录后轮询，并可被通知面板主动刷新 */
export function useUnreadCount() {
  const user = useSession((s) => s.user);
  const [count, setCount] = useState(0);

  const refresh = useCallback(async () => {
    if (!user) {
      setCount(0);
      return;
    }
    try {
      setCount(await repo.notifications.unreadCount());
    } catch {
      /* 轮询失败不打扰用户，保留上次数值 */
    }
  }, [user]);

  useEffect(() => {
    if (!user) {
      setCount(0);
      return;
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(timer);
  }, [user, refresh]);

  return { count, refresh };
}
