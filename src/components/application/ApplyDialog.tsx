import { useState } from 'react';
import type { Job } from '@/domain/models';
import { repo } from '@/data';
import { formatDateTime } from '@/domain/format';
import { LIMITS, validateNote } from '@/domain/validation';
import { useSession } from '@/stores/session';
import { FileUploader } from './FileUploader';
import { Button } from '@/components/ui/Button';
import { Field, Textarea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { toast } from '@/stores/toast';

interface ApplyDialogProps {
  job: Job;
  open: boolean;
  onClose: () => void;
  onSubmitted: () => void;
}

export function ApplyDialog({ job, open, onClose, onSubmitted }: ApplyDialogProps) {
  const user = useSession((s) => s.user);
  const setUser = useSession((s) => s.setUser);
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState('');
  const [consentChecked, setConsentChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const needsConsent = !!user && !user.privacyConsented;

  const reset = () => {
    setFile(null);
    setNote('');
    setConsentChecked(false);
  };

  const submit = async () => {
    if (!file) {
      toast.error('请先上传简历文件');
      return;
    }
    const noteErr = validateNote(note);
    if (noteErr) {
      toast.error(noteErr);
      return;
    }
    if (needsConsent && !consentChecked) {
      toast.error('请先勾选同意个人信息处理告知');
      return;
    }
    setSubmitting(true);
    try {
      // 仅用户主动确认后，才向后端确认个人信息处理告知
      if (needsConsent) {
        const u = await repo.auth.confirmPrivacyConsent();
        setUser(u);
      }
      await repo.applications.submit({ jobId: job.id, resumeFile: file, note });
      toast.success('申请提交成功，状态为「处理中」');
      reset();
      onSubmitted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="申请加入"
      description={`「${job.title}」· 截止 ${formatDateTime(job.deadline)}`}
      width="max-w-xl"
      footer={
        <>
          <Button
            variant="secondary"
            onClick={() => {
              reset();
              onClose();
            }}
          >
            取消
          </Button>
          <Button onClick={submit} loading={submitting} disabled={!file}>
            提交申请
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <p className="rounded-md bg-page px-3.5 py-2.5 text-xs leading-relaxed text-ink2">
          同一招聘不可重复投递；撤回后可重新申请。
        </p>

        <Field label="简历文件" required>
          <FileUploader value={file} onChange={setFile} />
        </Field>

        <Field label="补充说明（选填）" hint={`不超过 ${LIMITS.note} 字`}>
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="请输入补充说明"
            maxLength={LIMITS.note}
          />
          <div className="text-right text-xs text-muted">
            {note.length}/{LIMITS.note}
          </div>
        </Field>

        {needsConsent && (
          <label className="flex cursor-pointer items-start gap-2.5 rounded-md bg-warning-soft px-3.5 py-3 text-xs leading-relaxed text-ink2">
            <input
              type="checkbox"
              checked={consentChecked}
              onChange={(e) => setConsentChecked(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              我已阅读并同意《个人信息处理告知》，同意平台为本次申请处理我的简历信息。
            </span>
          </label>
        )}
      </div>
    </Modal>
  );
}
