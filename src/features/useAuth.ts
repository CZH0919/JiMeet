import { useCallback, useEffect } from 'react';
import { repo } from '@/data';
import { useSession } from '@/stores/session';
import { toast } from '@/stores/toast';
import type { LoginInput, RegisterInput } from '@/domain/validation';

/**
 * 会话恢复只执行一次：页头、路由守卫、页面各自调用 useAuth 时不会重复请求 /me。
 * 模块级 promise 在应用生命周期内复用。
 */
let restorePromise: Promise<void> | null = null;

export function useAuth() {
  const user = useSession((s) => s.user);
  const ready = useSession((s) => s.ready);
  const setUser = useSession((s) => s.setUser);
  const setReady = useSession((s) => s.setReady);

  // 应用启动时恢复会话（GET /me）
  useEffect(() => {
    if (ready) return;
    if (!restorePromise) {
      restorePromise = repo.auth
        .getCurrentUser()
        .then(setUser)
        .catch(() => setUser(null))
        .finally(() => setReady(true));
    }
  }, [ready, setUser, setReady]);

  // 任意请求返回 401 时清空登录态（会话过期、后端重启等）
  useEffect(() => {
    const onUnauthenticated = () => setUser(null);
    window.addEventListener('jiyu:unauthenticated', onUnauthenticated);
    return () => window.removeEventListener('jiyu:unauthenticated', onUnauthenticated);
  }, [setUser]);

  const login = useCallback(
    async (input: LoginInput) => {
      const u = await repo.auth.login(input);
      setUser(u);
      toast.success(`欢迎回来，${u.name}`);
      return u;
    },
    [setUser],
  );

  const register = useCallback(
    async (input: RegisterInput) => {
      const u = await repo.auth.register(input);
      setUser(u);
      toast.success('注册成功，已为你登录');
      return u;
    },
    [setUser],
  );

  const devLogin = useCallback(
    async (realId: string) => {
      const u = await repo.auth.devLogin(realId);
      setUser(u);
      toast.success(`开发身份：${u.name}`);
      return u;
    },
    [setUser],
  );

  const logout = useCallback(async () => {
    try {
      await repo.auth.logout();
    } catch {
      // 会话可能已失效：仍然清理本地登录态
    }
    setUser(null);
    toast.info('已退出登录');
  }, [setUser]);

  const updateNickname = useCallback(
    async (nickname: string) => {
      const u = await repo.auth.updateProfile({ nickname });
      setUser(u);
      toast.success('昵称已更新');
      return u;
    },
    [setUser],
  );

  const consentPrivacy = useCallback(async () => {
    const u = await repo.auth.confirmPrivacyConsent();
    setUser(u);
    toast.success('已确认个人信息处理告知');
    return u;
  }, [setUser]);

  return { user, ready, login, register, devLogin, logout, updateNickname, consentPrivacy };
}
