import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/features/useAuth';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { toast } from '@/stores/toast';

const IMPACTS = [
  '所有设备上的登录状态将立即失效，原邮箱可重新注册新账号。',
  '未结束的招聘停止招募；本人投出的处理中申请按撤回处理，已录取结果仅保留统计。',
  '个人资料、简历访问权限、本人投稿及发出的聊天正文将被清除。',
  '已发布的招聘与公告显示为“已注销用户”，且不可恢复。',
];

/** 本人注销账号：展示影响并取得明确确认后提交 DELETE /me。 */
export function CancelAccountDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, cancelAccount } = useAuth();
  const navigate = useNavigate();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);

  const close = () => {
    if (busy) return;
    setChecked(false);
    onClose();
  };

  const submit = async () => {
    if (!checked || busy) return;
    setBusy(true);
    try {
      await cancelAccount();
      setChecked(false);
      onClose();
      navigate('/login', { replace: true });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '注销失败，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title="注销账号"
      description="该操作不可恢复，请确认已了解以下影响。"
      onClose={close}
      footer={
        <>
          <Button variant="secondary" onClick={close} disabled={busy}>
            取消
          </Button>
          <Button variant="danger" disabled={!checked} loading={busy} onClick={submit}>
            确认注销
          </Button>
        </>
      }
    >
      <ul className="flex flex-col gap-2 text-sm leading-relaxed text-ink2">
        {IMPACTS.map((text) => (
          <li key={text} className="flex gap-2">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-danger" />
            {text}
          </li>
        ))}
      </ul>
      <label className="mt-4 flex cursor-pointer items-start gap-2.5 rounded-md border border-danger/25 bg-danger-soft/40 px-3.5 py-3 text-xs leading-relaxed text-ink2">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
          className="mt-0.5"
        />
        我已了解上述影响，确认注销当前账号（{user?.email ?? user?.name ?? '当前账号'}）。
      </label>
    </Modal>
  );
}
