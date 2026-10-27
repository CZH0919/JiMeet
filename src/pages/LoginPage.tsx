import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { clsx } from 'clsx';
import { GraduationCap, ShieldCheck } from 'lucide-react';
import { useAuth } from '@/features/useAuth';
import { validateLoginEmail, validateLoginPassword } from '@/domain/validation';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { toast } from '@/stores/toast';

type Tab = 'email' | 'identity';

const DEMO_USERS = [
  { id: '20230001', name: '张同学', role: '学生', isAdmin: true },
  { id: '20230002', name: '李同学', role: '学生', isAdmin: false },
  { id: '20230003', name: '赵同学', role: '学生', isAdmin: false },
  { id: '20230004', name: '陈同学', role: '学生', isAdmin: false },
  { id: 'T2024001', name: '王老师', role: '教师', isAdmin: false },
  { id: 'T2024002', name: '刘老师', role: '教师', isAdmin: false },
];

export function LoginPage() {
  const [tab, setTab] = useState<Tab>('identity');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [loading, setLoading] = useState(false);
  const [identityLoading, setIdentityLoading] = useState(false);
  const { loginWithEmail, loginViaIdentity, loginAs } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const submitEmail = async () => {
    const e = {
      email: validateLoginEmail(email) ?? undefined,
      password: validateLoginPassword(password) ?? undefined,
    };
    setErrors(e);
    if (e.email || e.password) return;
    setLoading(true);
    try {
      await loginWithEmail(email);
      navigate(from, { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const submitIdentity = async () => {
    setIdentityLoading(true);
    try {
      await loginViaIdentity();
      navigate(from, { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '统一身份认证服务暂时不可用，请稍后重试');
    } finally {
      setIdentityLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-[#EAF3FC] to-page px-4 py-10">
      <div className="w-full max-w-md">
        <div className="rounded-xl border border-line bg-surface p-8 shadow-pop">
          <div className="mb-2 flex flex-col items-center">
            <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-xl bg-primary text-3xl font-semibold text-white">
              济
            </div>
            <h1 className="text-2xl font-semibold text-ink">济遇</h1>
            <p className="mt-1 text-sm text-ink2">登录后开启科创组队与招聘协作</p>
          </div>

          <div className="mb-6 flex rounded-md bg-page p-1">
            {(
              [
                { key: 'email', label: '邮箱登录' },
                { key: 'identity', label: '统一身份认证登录' },
              ] as { key: Tab; label: string }[]
            ).map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={clsx(
                  'flex-1 rounded px-3 py-2 text-sm font-medium transition-colors',
                  tab === t.key ? 'bg-surface text-primary shadow-card' : 'text-ink2 hover:text-ink',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'email' ? (
            <div className="flex flex-col gap-4">
              <Field label="邮箱" error={errors.email}>
                <Input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="请输入邮箱"
                  invalid={!!errors.email}
                />
              </Field>
              <Field label="密码" error={errors.password}>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="请输入密码"
                  invalid={!!errors.password}
                  onKeyDown={(e) => e.key === 'Enter' && submitEmail()}
                />
              </Field>
              <Button size="lg" loading={loading} onClick={submitEmail}>
                登录
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <Button size="lg" loading={identityLoading} onClick={submitIdentity}>
                <ShieldCheck size={18} /> 使用同济大学统一身份认证登录
              </Button>
              <p className="text-center text-xs leading-relaxed text-ink2">
                登录后自动区分教师/学生身份，身份仅在个人主页标注，业务逻辑完全一致
              </p>
            </div>
          )}
        </div>

        <div className="mt-6 rounded-xl border border-line bg-surface p-5">
          <p className="mb-3 flex items-center gap-1.5 text-sm font-medium text-ink">
            <GraduationCap size={16} /> 演示模式 · 快速切换身份
          </p>
          <div className="grid grid-cols-3 gap-2">
            {DEMO_USERS.map((u) => (
              <button
                key={u.id}
                onClick={async () => {
                  await loginAs(u.id);
                  navigate(from, { replace: true });
                }}
                className="flex flex-col items-center rounded-md border border-line py-2.5 text-xs hover:border-primary hover:bg-primary-soft"
              >
                <span className="font-medium text-ink">{u.name}</span>
                <span className="mt-0.5 text-ink2">
                  {u.isAdmin ? '管理员·' : ''}
                  {u.role}
                </span>
              </button>
            ))}
          </div>
        </div>

        <p className="mt-8 text-center text-xs text-muted">
          2026 济遇 Jiyu · 校园科创招聘组队平台 版权所有
        </p>
      </div>
    </div>
  );
}
