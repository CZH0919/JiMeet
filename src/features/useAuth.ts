import { useCallback, useEffect } from 'react';
import { repo } from '@/data';
import { useSession } from '@/stores/session';
import { toast } from '@/stores/toast';

export function useAuth() {
  const user = useSession((s) => s.user);
  const ready = useSession((s) => s.ready);
  const setUser = useSession((s) => s.setUser);
  const setReady = useSession((s) => s.setReady);

  // 应用启动时恢复会话
  useEffect(() => {
    if (ready) return;
    repo.auth
      .getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, [ready, setUser, setReady]);

  const loginWithEmail = useCallback(
    async (email: string) => {
      const u = await repo.auth.loginWithEmail(email);
      setUser(u);
      toast.success(`欢迎回来，${u.name}`);
      return u;
    },
    [setUser],
  );

  const loginViaIdentity = useCallback(async () => {
    const u = await repo.auth.login();
    setUser(u);
    toast.success(`统一身份认证成功，欢迎 ${u.name}`);
    return u;
  }, [setUser]);

  const loginAs = useCallback(
    async (userId: string) => {
      const u = await repo.auth.loginAs(userId);
      setUser(u);
      toast.success(`已切换为 ${u.name}（${u.isAdmin ? '管理员·' : ''}${u.role === 'student' ? '学生' : '教师'}）`);
      return u;
    },
    [setUser],
  );

  const logout = useCallback(async () => {
    await repo.auth.logout();
    setUser(null);
    toast.info('已退出登录');
  }, [setUser]);

  return { user, ready, loginWithEmail, loginViaIdentity, loginAs, logout };
}
