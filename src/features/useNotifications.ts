import { useEffect, useState } from 'react';
import { repo } from '@/data';
import { useSession } from '@/stores/session';

export function useUnreadCount() {
  const user = useSession((s) => s.user);
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!user) {
      setCount(0);
      return;
    }
    let alive = true;
    const load = () =>
      repo.notifications.unreadCount().then((n) => alive && setCount(n));
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [user]);

  return count;
}
