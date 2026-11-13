import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/features/useAuth';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { toast } from '@/stores/toast';

export function LoginPage() {
  const [realId, setRealId] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const { devLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const submit = async () => {
    const id = realId.trim();
    if (!id) {
      setError('请输入登录编号');
      return;
    }
    setError(undefined);
    setLoading(true);
    try {
      await devLogin(id);
      navigate(from, { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
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

          <div className="flex flex-col gap-4">
            <Field label="登录编号" error={error}>
              <Input
                value={realId}
                onChange={(e) => {
                  setRealId(e.target.value);
                  setError(undefined);
                }}
                placeholder="请输入编号（T/t 开头为教师）"
                invalid={!!error}
                onKeyDown={(e) => e.key === 'Enter' && submit()}
              />
            </Field>
            <Button size="lg" loading={loading} onClick={submit}>
              登录
            </Button>
            <p className="text-center text-xs leading-relaxed text-ink2">
              开发阶段使用编号登录；以 T/t 开头的编号映射为教师身份，其余为学生身份。
              <br />
              正式统一身份认证尚未接入。
            </p>
          </div>
        </div>

        <p className="mt-8 text-center text-xs text-muted">
          2026 济遇 Jiyu · 校园科创招聘组队平台 版权所有
        </p>
      </div>
    </div>
  );
}
