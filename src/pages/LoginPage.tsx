import { useEffect, useState } from 'react';
import type { KeyboardEventHandler } from 'react';
import { Check, Link as LinkIcon } from 'lucide-react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { clsx } from 'clsx';
import { repo } from '@/data';
import { ApiError, fieldErrorsFrom } from '@/data/http/client';
import { useAuth } from '@/features/useAuth';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { PasswordInput } from '@/components/ui/PasswordInput';
import { Logo } from '@/components/layout/Logo';
import {
  CODE_RESEND_SECONDS,
  EMAIL_SUFFIX,
  FIELD_HINT,
  PASSWORD_HINT,
  PASSWORD_MESSAGES,
  toTongjiEmail,
  validateAccountId,
  validateCode,
  validateName,
  validatePassword,
  type LoginCodeErrors,
  type LoginCodeForm,
  type LoginPasswordErrors,
  type LoginPasswordForm,
  type RegisterErrors,
  type RegisterForm,
} from '@/domain/validation';
import type { UserRole } from '@/domain/models';
import { toast } from '@/stores/toast';

type Mode = 'login' | 'register';
type LoginMethod = 'password' | 'code';
type RegisterStep = 'email' | 'code' | 'profile';

const FEATURES = [
  '同济邮箱验证码注册，设置自己的登录密码',
  '竞赛组队与校内活动招聘一屏发现',
  '上传 PDF / DOC 简历，一键投递并可随时撤回',
];

const STEP_LABEL: Record<RegisterStep, string> = {
  email: '邮箱验证',
  code: '输入验证码',
  profile: '设置密码',
};

/** 倒计时：到期后允许再次请求验证码 */
function useResendCountdown() {
  const [endsAt, setEndsAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (endsAt <= Date.now()) return;
    const timer = window.setInterval(() => {
      // 到期后停止计时，避免空转
      if (Date.now() >= endsAt) {
        window.clearInterval(timer);
      }
      setNow(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [endsAt]);

  return {
    remaining: Math.max(0, Math.ceil((endsAt - now) / 1000)),
    start(seconds: number) {
      setNow(Date.now());
      setEndsAt(Date.now() + seconds * 1000);
    },
  };
}

/** 邮箱前缀输入框：右侧固定展示 @tongji.edu.cn 后缀 */
function AccountInput({
  value,
  onChange,
  invalid,
  onKeyDown,
  autoFocus,
  readOnly,
  autoComplete = 'username',
}: {
  value: string;
  onChange: (v: string) => void;
  invalid?: boolean;
  onKeyDown?: KeyboardEventHandler<HTMLInputElement>;
  autoFocus?: boolean;
  readOnly?: boolean;
  autoComplete?: string;
}) {
  return (
    <div
      className={clsx(
        'flex items-stretch overflow-hidden rounded-md border bg-surface transition-colors',
        'focus-within:border-primary focus-within:ring-4 focus-within:ring-primary/10',
        invalid ? 'border-danger' : 'border-line',
        readOnly && 'bg-page',
      )}
    >
      <input
        className="min-w-0 flex-1 bg-transparent px-3.5 py-2.5 text-sm text-ink outline-none placeholder:text-muted disabled:text-ink2"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="邮箱前缀，如 2151234"
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        onKeyDown={onKeyDown}
        readOnly={readOnly}
        aria-label="邮箱前缀"
      />
      <span className="flex select-none items-center border-l border-line bg-page px-3 text-[13px] text-ink2">
        {EMAIL_SUFFIX}
      </span>
    </div>
  );
}

/** 验证码输入框：6 位数字，保留前导零 */
function CodeInput({
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
    <input
      className={clsx(
        'w-full rounded-md border bg-surface px-3.5 py-2.5 text-center text-lg font-semibold tracking-[0.5em] text-ink',
        'placeholder:text-sm placeholder:font-normal placeholder:tracking-normal placeholder:text-muted',
        'transition-colors focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/10',
        invalid ? 'border-danger' : 'border-line',
      )}
      inputMode="numeric"
      autoComplete="one-time-code"
      maxLength={6}
      placeholder="6 位数字验证码"
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
      onKeyDown={onKeyDown}
      autoFocus={autoFocus}
      aria-label="邮箱验证码"
    />
  );
}

function StepDots({ step }: { step: RegisterStep }) {
  const order: RegisterStep[] = ['email', 'code', 'profile'];
  const index = order.indexOf(step);
  return (
    <ol className="flex items-center gap-2">
      {order.map((s, i) => {
        const done = i < index;
        const active = i === index;
        return (
          <li key={s} className="flex flex-1 items-center gap-2">
            <span
              className={clsx(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
                done && 'bg-primary text-white',
                active && 'bg-primary-soft text-primary ring-2 ring-primary/25',
                !done && !active && 'bg-muted-soft text-muted',
              )}
            >
              {done ? <Check size={13} /> : i + 1}
            </span>
            <span
              className={clsx(
                'whitespace-nowrap text-xs',
                active ? 'font-medium text-ink' : 'text-ink2',
              )}
            >
              {STEP_LABEL[s]}
            </span>
            {i < order.length - 1 && <span className="h-px flex-1 bg-line" />}
          </li>
        );
      })}
    </ol>
  );
}

export function LoginPage() {
  const { user, login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const [mode, setMode] = useState<Mode>('login');
  const [method, setMethod] = useState<LoginMethod>('password');
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'info' | 'warning'; text: string } | null>(null);
  /** 邮箱已注册：验码成功后才由服务端提示，此时不再展示建号资格 */
  const [existingAccount, setExistingAccount] = useState(false);

  const [loginForm, setLoginForm] = useState<LoginPasswordForm>({ accountId: '', password: '' });
  const [loginCodeForm, setLoginCodeForm] = useState<LoginCodeForm>({ accountId: '', code: '' });
  const [loginErrors, setLoginErrors] = useState<LoginPasswordErrors>({});
  const [loginCodeErrors, setLoginCodeErrors] = useState<LoginCodeErrors>({});

  const [regStep, setRegStep] = useState<RegisterStep>('email');
  const [regForm, setRegForm] = useState<RegisterForm>({
    accountId: '',
    code: '',
    password: '',
    confirm: '',
    name: '',
    nickname: '',
    role: 'student',
  });
  const [regErrors, setRegErrors] = useState<RegisterErrors>({});

  const regResend = useResendCountdown();
  const loginResend = useResendCountdown();

  if (user) return <Navigate to={from} replace />;

  const fail = (e: unknown, fallback: string) => {
    const message = e instanceof Error ? e.message : fallback;
    setSubmitError(message);
    toast.error(message);
  };

  /**
   * 后端字段级错误落到对应输入框，页面顶部不再重复展示同一句提示。
   * 返回是否至少命中一个字段（命中时不再弹 toast）。
   */
  const applyServerErrors = (error: unknown, mapping: Record<string, (msg: string) => void>): boolean => {
    const fields = fieldErrorsFrom(error);
    let applied = false;
    for (const [field, setter] of Object.entries(mapping)) {
      const message = fields[field];
      if (!message) continue;
      setter(message);
      applied = true;
    }
    return applied;
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setSubmitError(null);
    setNotice(null);
    setExistingAccount(false);
  };

  const goLogin = (accountId: string) => {
    setLoginForm({ accountId, password: '' });
    setLoginCodeForm({ accountId, code: '' });
    setLoginErrors({});
    setLoginCodeErrors({});
    setSubmitError(null);
    setNotice(null);
    setExistingAccount(false);
    // 离开注册流程时清空验证码与密码，避免切回注册页停留在失效步骤
    setRegStep('email');
    setRegForm((f) => ({ ...f, code: '', password: '', confirm: '' }));
    setRegErrors({});
    setMode('login');
  };

  /* ------------------------------- 登录 ------------------------------- */

  const submitPasswordLogin = async () => {
    // 优先级：先只提示邮箱，再提示密码，避免一次抛出多条不相干错误
    const errors: LoginPasswordErrors = {};
    const account = validateAccountId(loginForm.accountId);
    if (account) errors.accountId = account;
    else if (!loginForm.password) errors.password = PASSWORD_MESSAGES.required;
    setLoginErrors(errors);
    setSubmitError(null);
    if (Object.keys(errors).length > 0) return;

    setLoading(true);
    try {
      await login({ email: toTongjiEmail(loginForm.accountId), password: loginForm.password });
      navigate(from, { replace: true });
    } catch (e) {
      const applied = applyServerErrors(e, {
        email: (msg) => setLoginErrors((errs) => ({ ...errs, accountId: msg })),
        password: (msg) => setLoginErrors((errs) => ({ ...errs, password: msg })),
      });
      if (!applied) fail(e, '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const sendLoginCode = async () => {
    const account = validateAccountId(loginCodeForm.accountId);
    if (account) {
      setLoginCodeErrors({ accountId: account });
      return;
    }
    setLoginCodeErrors({});
    setSubmitError(null);
    setLoading(true);
    try {
      const result = await repo.auth.sendLoginCode(toTongjiEmail(loginCodeForm.accountId));
      loginResend.start(result.resendAfter || CODE_RESEND_SECONDS);
      setNotice({
        tone: 'info',
        text: `验证码已发送至 ${toTongjiEmail(loginCodeForm.accountId)}，5 分钟内有效。`,
      });
    } catch (e) {
      fail(e, '验证码发送失败');
    } finally {
      setLoading(false);
    }
  };

  const submitCodeLogin = async () => {
    const errors: LoginCodeErrors = {};
    const account = validateAccountId(loginCodeForm.accountId);
    if (account) errors.accountId = account;
    else {
      const code = validateCode(loginCodeForm.code);
      if (code) errors.code = code;
    }
    setLoginCodeErrors(errors);
    setSubmitError(null);
    if (Object.keys(errors).length > 0) return;

    setLoading(true);
    try {
      await login({ email: toTongjiEmail(loginCodeForm.accountId), code: loginCodeForm.code.trim() });
      navigate(from, { replace: true });
    } catch (e) {
      const applied = applyServerErrors(e, {
        email: (msg) => setLoginCodeErrors((errs) => ({ ...errs, accountId: msg })),
        code: (msg) => setLoginCodeErrors((errs) => ({ ...errs, code: msg })),
      });
      if (!applied) fail(e, '登录失败');
    } finally {
      setLoading(false);
    }
  };

  /* ------------------------------- 注册 ------------------------------- */

  const sendRegisterCode = async () => {
    // 第一步只校验邮箱；缺少验证码的提示留到验码步骤
    const account = validateAccountId(regForm.accountId);
    if (account) {
      setRegErrors({ accountId: account });
      return;
    }
    setRegErrors({});
    setSubmitError(null);
    setLoading(true);
    try {
      const result = await repo.auth.sendRegisterCode(toTongjiEmail(regForm.accountId));
      regResend.start(result.resendAfter || CODE_RESEND_SECONDS);
      setRegStep('code');
      setExistingAccount(false);
      setRegForm((f) => ({ ...f, code: '' }));
      // 验证码步骤顶部已有「已发送至…」说明，不再重复一条 notice
      setNotice(null);
    } catch (e) {
      fail(e, '验证码发送失败');
    } finally {
      setLoading(false);
    }
  };

  const verifyRegisterCode = async () => {
    // 只提示验证码本身；邮箱是否已注册在验码成功后才由服务端告知
    const code = validateCode(regForm.code);
    if (code) {
      setRegErrors({ code });
      return;
    }
    setRegErrors({});
    setSubmitError(null);
    setNotice(null);
    setLoading(true);
    try {
      const result = await repo.auth.verifyRegisterCode(toTongjiEmail(regForm.accountId), regForm.code);
      if (result.accountExists) {
        setExistingAccount(true);
        setNotice({ tone: 'warning', text: '该邮箱已注册，请直接登录。' });
        return;
      }
      setExistingAccount(false);
      setRegStep('profile');
      // 第三步顶部已显示「邮箱已验证」，不再重复提示
      setNotice(null);
    } catch (e) {
      const applied = applyServerErrors(e, {
        code: (msg) => setRegErrors((errs) => ({ ...errs, code: msg })),
        email: (msg) => setRegErrors((errs) => ({ ...errs, accountId: msg })),
      });
      if (!applied) fail(e, '验证码校验失败');
    } finally {
      setLoading(false);
    }
  };

  const submitRegister = async () => {
    const errors: RegisterErrors = {};

    const name = regForm.name.trim();
    const nameError = validateName(name);
    if (nameError) errors.name = nameError;

    if (regForm.nickname.trim().length > 32) errors.nickname = '昵称不超过 32 字';

    const email = toTongjiEmail(regForm.accountId);
    const password = validatePassword(regForm.password, { email, name });
    if (password) errors.password = password;
    if (!errors.password && regForm.confirm !== regForm.password) {
      errors.confirm = '两次输入的密码不一致';
    }

    setRegErrors(errors);
    setSubmitError(null);
    if (Object.keys(errors).length > 0) return;

    setLoading(true);
    try {
      await register({
        email,
        password: regForm.password,
        passwordConfirm: regForm.confirm,
        name,
        nickname: regForm.nickname.trim(),
        role: regForm.role,
      });
      navigate(from, { replace: true });
    } catch (e) {
      // 资格已失效或被抢先注册：回到验证码步骤，而不是让用户停在无解的密码页
      if (e instanceof ApiError) {
        const fields = fieldErrorsFrom(e);
        if (fields.verification) {
          setRegStep('code');
          setNotice({ tone: 'warning', text: '邮箱验证已失效，请重新获取验证码。' });
          setLoading(false);
          return;
        }
        if (fields.email) {
          setNotice({ tone: 'warning', text: '该邮箱已注册，请直接登录。' });
          setLoading(false);
          return;
        }
      }
      const applied = applyServerErrors(e, {
        password: (msg) => setRegErrors((errs) => ({ ...errs, password: msg })),
        password_confirm: (msg) => setRegErrors((errs) => ({ ...errs, confirm: msg })),
        name: (msg) => setRegErrors((errs) => ({ ...errs, name: msg })),
        nickname: (msg) => setRegErrors((errs) => ({ ...errs, nickname: msg })),
        email: (msg) => setRegErrors((errs) => ({ ...errs, accountId: msg })),
      });
      if (!applied) fail(e, '注册失败');
    } finally {
      setLoading(false);
    }
  };

  const resetRegisterEmail = () => {
    setRegStep('email');
    setRegForm((f) => ({ ...f, code: '' }));
    setRegErrors({});
    setExistingAccount(false);
    setNotice(null);
    setSubmitError(null);
  };

  const noticeTone =
    notice?.tone === 'warning'
      ? 'border-warning/30 bg-warning-soft text-ink'
      : 'border-primary/20 bg-primary-soft text-ink';

  return (
    <div className="flex min-h-screen flex-col">
      <header className="page-shell flex h-[72px] items-center justify-between">
        <Logo />
        <Link
          to="/"
          className="inline-flex h-9 items-center rounded-full border border-line bg-surface px-5 text-sm text-ink transition-colors hover:border-primary/40 hover:text-primary"
        >
          返回首页
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
                  onClick={() => switchMode(m)}
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
                <div className="flex gap-1 rounded-md border border-line p-1">
                  {(
                    [
                      { key: 'password', label: '密码登录' },
                      { key: 'code', label: '验证码登录' },
                    ] as { key: LoginMethod; label: string }[]
                  ).map((m) => (
                    <button
                      key={m.key}
                      type="button"
                      onClick={() => {
                        setMethod(m.key);
                        setSubmitError(null);
                        setNotice(null);
                      }}
                      className={clsx(
                        'flex-1 rounded-sm py-1.5 text-xs font-medium transition-colors',
                        method === m.key
                          ? 'bg-primary-soft text-primary'
                          : 'text-ink2 hover:bg-muted-soft',
                      )}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>

                {method === 'password' ? (
                  <>
                    <Field label="邮箱" required error={loginErrors.accountId}>
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
                      <PasswordInput
                        autoComplete="current-password"
                        value={loginForm.password}
                        onChange={(e) => {
                          setLoginForm((f) => ({ ...f, password: e.target.value }));
                          setLoginErrors((errs) => ({ ...errs, password: undefined }));
                        }}
                        placeholder="请输入密码"
                        invalid={!!loginErrors.password}
                        onKeyDown={(e) => e.key === 'Enter' && void submitPasswordLogin()}
                      />
                    </Field>

                    {submitError && (
                      <p className="rounded-md bg-danger-soft px-3.5 py-2.5 text-xs leading-relaxed text-danger">
                        {submitError}
                      </p>
                    )}

                    <Button size="lg" className="mt-1 w-full rounded-full" loading={loading} onClick={submitPasswordLogin}>
                      登录
                    </Button>
                  </>
                ) : (
                  <>
                    <Field label="邮箱" required error={loginCodeErrors.accountId}>
                      <AccountInput
                        value={loginCodeForm.accountId}
                        onChange={(accountId) => {
                          setLoginCodeForm((f) => ({ ...f, accountId }));
                          setLoginCodeErrors((errs) => ({ ...errs, accountId: undefined }));
                          if (notice?.tone === 'info') setNotice(null);
                        }}
                        invalid={!!loginCodeErrors.accountId}
                        autoFocus
                      />
                    </Field>
                    <Field
                      label="验证码"
                      required
                      error={loginCodeErrors.code}
                      hint={
                        loginResend.remaining > 0
                          ? `${loginResend.remaining} 秒后可重新发送`
                          : '6 位数字，5 分钟内有效'
                      }
                    >
                      <div className="flex items-center gap-2">
                        <CodeInput
                          value={loginCodeForm.code}
                          onChange={(code) => {
                            setLoginCodeForm((f) => ({ ...f, code }));
                            setLoginCodeErrors((errs) => ({ ...errs, code: undefined }));
                          }}
                          invalid={!!loginCodeErrors.code}
                          onKeyDown={(e) => e.key === 'Enter' && void submitCodeLogin()}
                        />
                        <Button
                          variant="secondary"
                          className="shrink-0 whitespace-nowrap"
                          disabled={loginResend.remaining > 0}
                          loading={loading}
                          onClick={sendLoginCode}
                        >
                          {loginResend.remaining > 0 ? `${loginResend.remaining}s` : '发送验证码'}
                        </Button>
                      </div>
                    </Field>

                    {notice && (
                      <p className={clsx('rounded-md border px-3.5 py-2.5 text-xs leading-relaxed', noticeTone)}>
                        {notice.text}
                      </p>
                    )}
                    {submitError && (
                      <p className="rounded-md bg-danger-soft px-3.5 py-2.5 text-xs leading-relaxed text-danger">
                        {submitError}
                      </p>
                    )}

                    <Button size="lg" className="mt-1 w-full rounded-full" loading={loading} onClick={submitCodeLogin}>
                      登录
                    </Button>
                  </>
                )}

                <p className="text-center text-xs text-ink2">
                  还没有账号？
                  <button
                    type="button"
                    onClick={() => switchMode('register')}
                    className="ml-1 font-medium text-primary hover:underline"
                  >
                    立即注册
                  </button>
                </p>
              </div>
            ) : (
              <div className="mt-6 flex flex-col gap-4">
                <StepDots step={regStep} />

                {regStep === 'email' && (
                  <>
                    <p className="rounded-md bg-page px-3.5 py-2.5 text-xs leading-relaxed text-ink2">
                      注册需先验证同济邮箱，验证通过后设置登录密码。
                    </p>
                    <Field label="同济邮箱" required error={regErrors.accountId}>
                      <AccountInput
                        value={regForm.accountId}
                        onChange={(accountId) => {
                          setRegForm((f) => ({ ...f, accountId }));
                          setRegErrors((errs) => ({ ...errs, accountId: undefined }));
                        }}
                        invalid={!!regErrors.accountId}
                        autoFocus
                        onKeyDown={(e) => e.key === 'Enter' && void sendRegisterCode()}
                      />
                    </Field>

                    {submitError && (
                      <p className="rounded-md bg-danger-soft px-3.5 py-2.5 text-xs leading-relaxed text-danger">
                        {submitError}
                      </p>
                    )}

                    <Button size="lg" className="mt-1 w-full rounded-full" loading={loading} onClick={sendRegisterCode}>
                      发送验证码
                    </Button>
                    <p className="text-center text-xs text-ink2">
                      已有账号？
                      <button
                        type="button"
                        onClick={() => switchMode('login')}
                        className="ml-1 font-medium text-primary hover:underline"
                      >
                        直接登录
                      </button>
                    </p>
                  </>
                )}

                {regStep === 'code' && (
                  <>
                    <div className="rounded-md bg-page px-3.5 py-2.5 text-xs leading-6 text-ink2">
                      验证码已发送至{' '}
                      <span className="font-medium text-ink">{toTongjiEmail(regForm.accountId)}</span>
                    </div>

                    <Field
                      label="验证码"
                      required
                      error={regErrors.code}
                      hint={regResend.remaining > 0 ? `${regResend.remaining} 秒后可重新发送` : '6 位数字，5 分钟内有效'}
                    >
                      <CodeInput
                        value={regForm.code}
                        onChange={(code) => {
                          setRegForm((f) => ({ ...f, code }));
                          setRegErrors((errs) => ({ ...errs, code: undefined }));
                          if (notice?.tone === 'warning') setNotice(null);
                        }}
                        invalid={!!regErrors.code}
                        autoFocus
                        onKeyDown={(e) => e.key === 'Enter' && void verifyRegisterCode()}
                      />
                    </Field>

                    {notice && notice.text && (
                      <div className={clsx('rounded-md border px-3.5 py-2.5 text-xs leading-relaxed', noticeTone)}>
                        <p>{notice.text}</p>
                        {notice.tone === 'warning' && !existingAccount && (
                          <button
                            type="button"
                            onClick={() => goLogin(regForm.accountId)}
                            className="mt-1.5 inline-flex items-center gap-1 font-medium text-primary hover:underline"
                          >
                            <LinkIcon size={12} /> 去登录该邮箱
                          </button>
                        )}
                      </div>
                    )}
                    {submitError && (
                      <p className="rounded-md bg-danger-soft px-3.5 py-2.5 text-xs leading-relaxed text-danger">
                        {submitError}
                      </p>
                    )}

                    {existingAccount ? (
                      <>
                        <Button
                          size="lg"
                          className="w-full rounded-full"
                          onClick={() => goLogin(regForm.accountId)}
                        >
                          去登录该邮箱
                        </Button>
                        <Button variant="secondary" className="w-full rounded-full" onClick={resetRegisterEmail}>
                          换一个邮箱注册
                        </Button>
                      </>
                    ) : (
                      <>
                        <div className="flex gap-2">
                          <Button variant="secondary" className="flex-1 rounded-full" onClick={resetRegisterEmail}>
                            更换邮箱
                          </Button>
                          <Button
                            variant="secondary"
                            className="flex-1 rounded-full"
                            disabled={regResend.remaining > 0}
                            loading={loading}
                            onClick={sendRegisterCode}
                          >
                            {regResend.remaining > 0 ? `${regResend.remaining}s 后重发` : '重新发送'}
                          </Button>
                        </div>
                        <Button size="lg" className="w-full rounded-full" loading={loading} onClick={verifyRegisterCode}>
                          验证并继续
                        </Button>
                      </>
                    )}
                  </>
                )}

                {regStep === 'profile' && (
                  <>
                    <div className="flex items-center justify-between rounded-md bg-page px-3.5 py-2.5 text-xs text-ink2">
                      <span>
                        邮箱 <span className="font-medium text-ink">{toTongjiEmail(regForm.accountId)}</span> 已验证
                        <span className="text-muted"> · 请在 10 分钟内完成</span>
                      </span>
                      <button type="button" onClick={() => goLogin(regForm.accountId)} className="text-primary hover:underline">
                        不是我的邮箱
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <Field label="姓名" required error={regErrors.name} hint={FIELD_HINT.name}>
                        <Input
                          value={regForm.name}
                          onChange={(e) => {
                            setRegForm((f) => ({ ...f, name: e.target.value }));
                            setRegErrors((errs) => ({ ...errs, name: undefined }));
                          }}
                          placeholder="请填写姓名"
                          invalid={!!regErrors.name}
                          maxLength={32}
                          autoFocus
                        />
                      </Field>
                      <Field label="昵称（选填）" error={regErrors.nickname} hint={FIELD_HINT.nickname}>
                        <Input
                          value={regForm.nickname}
                          onChange={(e) => {
                            setRegForm((f) => ({ ...f, nickname: e.target.value }));
                            setRegErrors((errs) => ({ ...errs, nickname: undefined }));
                          }}
                          placeholder="留空由系统生成"
                          invalid={!!regErrors.nickname}
                          maxLength={32}
                        />
                      </Field>
                    </div>

                    <Field label="身份" required hint="仅用于界面展示与通知称谓，注册后不可自行修改">
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

                    <Field label="密码" required error={regErrors.password} hint={PASSWORD_HINT}>
                      <PasswordInput
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
                      <PasswordInput
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

                    {notice && notice.text && (
                      <div className={clsx('rounded-md border px-3.5 py-2.5 text-xs leading-relaxed', noticeTone)}>
                        <p>{notice.text}</p>
                        {notice.tone === 'warning' && (
                          <button
                            type="button"
                            onClick={() => goLogin(regForm.accountId)}
                            className="mt-1.5 font-medium text-primary hover:underline"
                          >
                            去登录该邮箱
                          </button>
                        )}
                      </div>
                    )}
                    {submitError && (
                      <p className="rounded-md bg-danger-soft px-3.5 py-2.5 text-xs leading-relaxed text-danger">
                        {submitError}
                      </p>
                    )}

                    <Button size="lg" className="mt-1 w-full rounded-full" loading={loading} onClick={submitRegister}>
                      注册并登录
                    </Button>
                    <p className="text-center text-[11px] leading-relaxed text-muted">
                      注册即表示同意《个人信息处理告知》，首次投递前需再次确认。
                    </p>
                  </>
                )}
              </div>
            )}
          </div>

          <p className="mt-6 text-center text-[11px] text-muted">
            济遇 Jiyu · 同济大学校内竞赛与活动招聘平台
          </p>
        </section>
      </div>
    </div>
  );
}
