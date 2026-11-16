import { useState } from 'react';
import type { KeyboardEventHandler } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { clsx } from 'clsx';
import { useAuth } from '@/features/useAuth';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { Logo } from '@/components/layout/Logo';
import {
  EMAIL_SUFFIX,
  toTongjiEmail,
  validateAccountId,
  validatePassword,
  type AccountLoginErrors,
  type AccountLoginForm,
  type AccountRegisterErrors,
  type AccountRegisterForm,
} from '@/domain/validation';
import type { UserRole } from '@/domain/models';
import { toast } from '@/stores/toast';

type Mode = 'login' | 'register';

const FEATURES = [
  '同济邮箱账号，学号直接登录',
  '竞赛组队、活动招聘、实验室实习一屏发现',
  '上传 PDF / DOC 简历，一键投递并可随时撤回',
];

/** 学号输入框：右侧固定展示 @tongji.edu.cn 后缀 */
function AccountInput({
  value,
  onChange,
  invalid,
  onKeyDown,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  invalid?: boolean;
  onKeyDown?: KeyboardEventHandler<HTMLInputElement>;
  autoFocus?: boolean;
}) {
  return (
    <div
      className={clsx(
        'flex items-stretch overflow-hidden rounded-md border bg-surface transition-colors',
        'focus-within:border-primary focus-within:ring-4 focus-within:ring-primary/10',
        invalid ? 'border-danger' : 'border-line',
      )}
    >
      <input
        className="min-w-0 flex-1 bg-transparent px-3.5 py-2.5 text-sm text-ink outline-none placeholder:text-muted"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="学号或工号，如 2151234"
        autoComplete="username"
        autoFocus={autoFocus}
        onKeyDown={onKeyDown}
        aria-label="学号或工号"
      />
      <span className="flex select-none items-center border-l border-line bg-page px-3 text-[13px] text-ink2">
        {EMAIL_SUFFIX}
      </span>
    </div>
  );
}

export function LoginPage() {
  const { user, login, register, devLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const [mode, setMode] = useState<Mode>('login');
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [devOpen, setDevOpen] = useState(false);
  const [devId, setDevId] = useState('');

  const [loginForm, setLoginForm] = useState<AccountLoginForm>({ accountId: '', password: '' });
  const [regForm, setRegForm] = useState<AccountRegisterForm>({
    accountId: '',
    password: '',
    name: '',
    nickname: '',
    role: 'student',
    confirm: '',
  });
  const [loginErrors, setLoginErrors] = useState<AccountLoginErrors>({});
  const [regErrors, setRegErrors] = useState<AccountRegisterErrors>({});

  if (user) return <Navigate to={from} replace />;

  const fail = (e: unknown, fallback: string) => {
    const message = e instanceof Error ? e.message : fallback;
    setSubmitError(message);
    toast.error(message);
  };

  const submitLogin = async () => {
    const errors: AccountLoginErrors = {};
    const account = validateAccountId(loginForm.accountId);
    if (account) errors.accountId = account;
    if (!loginForm.password) errors.password = '请输入密码';
    setLoginErrors(errors);
    setSubmitError(null);
    if (Object.keys(errors).length > 0) return;

    setLoading(true);
    try {
      await login({ email: toTongjiEmail(loginForm.accountId), password: loginForm.password });
      navigate(from, { replace: true });
    } catch (e) {
      fail(e, '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const submitRegister = async () => {
    const errors: AccountRegisterErrors = {};
    const account = validateAccountId(regForm.accountId);
    if (account) errors.accountId = account;

    const name = regForm.name.trim();
    if (!name) errors.name = '请输入姓名';
    else if (name.length > 32) errors.name = '姓名不超过 32 字';

    if (regForm.nickname.trim().length > 32) errors.nickname = '昵称不超过 32 字';

    const email = toTongjiEmail(regForm.accountId);
    const password = validatePassword(regForm.password, { email, name });
    if (password) errors.password = password;
    if (regForm.confirm !== regForm.password) errors.confirm = '两次输入的密码不一致';

    setRegErrors(errors);
    setSubmitError(null);
    if (Object.keys(errors).length > 0) return;

    setLoading(true);
    try {
      await register({
        email,
        password: regForm.password,
        name,
        nickname: regForm.nickname.trim(),
        role: regForm.role,
      });
      navigate(from, { replace: true });
    } catch (e) {
      fail(e, '注册失败');
    } finally {
      setLoading(false);
    }
  };

  const submitDev = async () => {
    const id = devId.trim();
    if (!id) {
      toast.error('请输入开发编号');
      return;
    }
    setSubmitError(null);
    setLoading(true);
    try {
      await devLogin(id);
      navigate(from, { replace: true });
    } catch (e) {
      fail(e, '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="page-shell flex h-[72px] items-center justify-between">
        <Logo />
        <Link
          to="/"
          className="inline-flex h-9 items-center rounded-full border border-line bg-surface px-5 text-sm text-ink transition-colors hover:border-primary/40 hover:text-primary"
        >
          先逛逛
        </Link>
      </header>

      <div className="page-shell grid flex-1 items-center gap-10 py-8 lg:grid-cols-2 lg:py-12">
        {/* 品牌区 */}
        <section className="hidden flex-col gap-6 lg:flex">
          <span className="inline-flex w-fit items-center gap-2 rounded-full bg-primary-soft px-3 py-1 text-xs font-medium text-primary">
            校内竞赛 &amp; 活动招聘平台
          </span>
          <h1 className="text-[40px] font-bold leading-[1.2] tracking-tight text-ink">
            在同济，遇见
            <br />
            一起做事的伙伴
          </h1>
          <p className="max-w-md text-[15px] leading-8 text-ink2">
            济遇把分散在学院网站、团委通知与群聊里的竞赛与活动信息集中到一处，
            让组队、发布招聘与投递简历都变得简单。
          </p>
          <ul className="flex flex-col gap-3">
            {FEATURES.map((f) => (
              <li key={f} className="flex items-center gap-2.5 text-sm text-ink2">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                {f}
              </li>
            ))}
          </ul>
        </section>

        {/* 表单区 */}
        <section className="mx-auto w-full max-w-[440px]">
          <div className="panel px-6 py-7 sm:px-8 sm:py-8">
            <div className="flex rounded-md bg-muted-soft p-1">
              {(['login', 'register'] as Mode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setMode(m);
                    setSubmitError(null);
                  }}
                  className={clsx(
                    'flex-1 rounded-sm py-2 text-sm font-medium transition-all',
                    mode === m ? 'bg-surface text-ink shadow-card' : 'text-ink2 hover:text-ink',
                  )}
                >
                  {m === 'login' ? '登录' : '注册'}
                </button>
              ))}
            </div>

            {mode === 'login' ? (
              <div className="mt-6 flex flex-col gap-4">
                <Field label="学号 / 工号" required error={loginErrors.accountId}>
                  <AccountInput
                    value={loginForm.accountId}
                    onChange={(accountId) => {
                      setLoginForm((f) => ({ ...f, accountId }));
                      setLoginErrors((errs) => ({ ...errs, accountId: undefined }));
                    }}
                    invalid={!!loginErrors.accountId}
                    autoFocus
                  />
                </Field>
                <Field label="密码" required error={loginErrors.password}>
                  <Input
                    type="password"
                    autoComplete="current-password"
                    value={loginForm.password}
                    onChange={(e) => {
                      setLoginForm((f) => ({ ...f, password: e.target.value }));
                      setLoginErrors((errs) => ({ ...errs, password: undefined }));
                    }}
                    placeholder="请输入密码"
                    invalid={!!loginErrors.password}
                    onKeyDown={(e) => e.key === 'Enter' && void submitLogin()}
                  />
                </Field>

                {submitError && (
                  <p className="rounded-md bg-danger-soft px-3.5 py-2.5 text-xs leading-relaxed text-danger">
                    {submitError}
                  </p>
                )}

                <Button size="lg" className="mt-1 w-full rounded-full" loading={loading} onClick={submitLogin}>
                  登录
                </Button>
                <p className="text-center text-xs text-ink2">
                  还没有账号？
                  <button
                    type="button"
                    onClick={() => {
                      setMode('register');
                      setSubmitError(null);
                    }}
                    className="ml-1 font-medium text-primary hover:underline"
                  >
                    立即注册
                  </button>
                </p>
              </div>
            ) : (
              <div className="mt-6 flex flex-col gap-4">
                <Field label="学号 / 工号" required error={regErrors.accountId}>
                  <AccountInput
                    value={regForm.accountId}
                    onChange={(accountId) => {
                      setRegForm((f) => ({ ...f, accountId }));
                      setRegErrors((errs) => ({ ...errs, accountId: undefined }));
                    }}
                    invalid={!!regErrors.accountId}
                    autoFocus
                  />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="姓名" required error={regErrors.name}>
                    <Input
                      value={regForm.name}
                      onChange={(e) => {
                        setRegForm((f) => ({ ...f, name: e.target.value }));
                        setRegErrors((errs) => ({ ...errs, name: undefined }));
                      }}
                      placeholder="本人资料使用"
                      invalid={!!regErrors.name}
                      maxLength={32}
                    />
                  </Field>
                  <Field label="昵称（选填）" error={regErrors.nickname}>
                    <Input
                      value={regForm.nickname}
                      onChange={(e) => {
                        setRegForm((f) => ({ ...f, nickname: e.target.value }));
                        setRegErrors((errs) => ({ ...errs, nickname: undefined }));
                      }}
                      placeholder="对外展示"
                      invalid={!!regErrors.nickname}
                      maxLength={32}
                    />
                  </Field>
                </div>

                <Field label="身份" required>
                  <div className="flex gap-2">
                    {(['student', 'teacher'] as UserRole[]).map((r) => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => setRegForm((f) => ({ ...f, role: r }))}
                        className={clsx(
                          'flex-1 rounded-md py-2 text-sm transition-colors',
                          regForm.role === r
                            ? 'bg-primary-soft font-medium text-primary'
                            : 'border border-line text-ink2 hover:border-primary/40',
                        )}
                      >
                        {r === 'student' ? '学生' : '教师'}
                      </button>
                    ))}
                  </div>
                </Field>

                <Field label="密码" required error={regErrors.password} hint="至少 8 位，不能全为数字或过于常见">
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={regForm.password}
                    onChange={(e) => {
                      setRegForm((f) => ({ ...f, password: e.target.value }));
                      setRegErrors((errs) => ({ ...errs, password: undefined }));
                    }}
                    placeholder="设置登录密码"
                    invalid={!!regErrors.password}
                  />
                </Field>
                <Field label="确认密码" required error={regErrors.confirm}>
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={regForm.confirm}
                    onChange={(e) => {
                      setRegForm((f) => ({ ...f, confirm: e.target.value }));
                      setRegErrors((errs) => ({ ...errs, confirm: undefined }));
                    }}
                    placeholder="再次输入密码"
                    invalid={!!regErrors.confirm}
                    onKeyDown={(e) => e.key === 'Enter' && void submitRegister()}
                  />
                </Field>

                {submitError && (
                  <p className="rounded-md bg-danger-soft px-3.5 py-2.5 text-xs leading-relaxed text-danger">
                    {submitError}
                  </p>
                )}

                <Button size="lg" className="mt-1 w-full rounded-full" loading={loading} onClick={submitRegister}>
                  注册并登录
                </Button>
                <p className="text-center text-[11px] leading-relaxed text-muted">
                  注册即表示同意《个人信息处理告知》，首次投递前需另行确认。
                </p>
              </div>
            )}
          </div>

          {import.meta.env.DEV && (
            <div className="mt-4 rounded-md border border-dashed border-line bg-surface/70 px-4 py-3">
              <button
                type="button"
                onClick={() => setDevOpen((v) => !v)}
                className="text-xs text-muted hover:text-ink"
              >
                {devOpen ? '收起开发调试登录' : '开发调试登录（仅本地联调）'}
              </button>
              {devOpen && (
                <div className="mt-3 flex gap-2">
                  <Input
                    value={devId}
                    onChange={(e) => setDevId(e.target.value)}
                    placeholder="开发编号，如 T2024001"
                    onKeyDown={(e) => e.key === 'Enter' && void submitDev()}
                  />
                  <Button variant="secondary" onClick={submitDev} loading={loading}>
                    登录
                  </Button>
                </div>
              )}
            </div>
          )}

          <p className="mt-6 text-center text-[11px] text-muted">
            济遇 Jiyu · 同济大学校内竞赛与活动招聘平台
          </p>
        </section>
      </div>
    </div>
  );
}
