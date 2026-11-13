import { useCallback, useEffect } from 'react';
import { repo } from '@/data';
import { useSession } from '@/stores/session';
import { toast } from '@/stores/toast';

export function useAuth() {
  const user = useSession((s) => s.user);
  const ready = useSession((s) => s.ready);
  const setUser = useSession((s) => s.setUser);
  const setReady = useSession((s) => s.setReady);

  // 应用启动时恢复会话（GET /me）
  useEffect(() => {
    if (ready) return;
    repo.auth
      .getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, [ready, setUser, setReady]);

  const devLogin = useCallback(
    async (realId: string) => {
      const u = await repo.auth.devLogin(realId);
      setUser(u);
      toast.success(`欢迎，${u.name}`);
      return u;
    },
    [setUser],
  );

  const logout = useCallback(async () => {
    await repo.auth.logout();
    setUser(null);
    toast.info('已退出登录');
  }, [setUser]);

  return { user, ready, devLogin, logout };
}
