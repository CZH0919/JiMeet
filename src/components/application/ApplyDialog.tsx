import { useState } from 'react';
import type { Job } from '@/domain/models';
import { repo } from '@/data';
import { validateNote } from '@/domain/validation';
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
      title={`申请加入【${job.title}】`}
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
        <p className="rounded-md bg-page px-3 py-2 text-xs leading-relaxed text-ink2">
          不可重复投递同一条未撤回申请；撤回后可重新投递；提交后生成全新申请记录
        </p>

        <Field label="上传简历文件" required>
          <FileUploader value={file} onChange={setFile} />
        </Field>

        <Field label="补充说明（选填，可留空）" hint="请输入你的相关经验、技能或加入理由">
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="请输入"
            maxLength={500}
          />
          <div className="text-right text-xs text-muted">{note.length}/500</div>
        </Field>

        {needsConsent && (
          <label className="flex cursor-pointer items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-xs leading-relaxed text-ink2">
            <input
              type="checkbox"
              checked={consentChecked}
              onChange={(e) => setConsentChecked(e.target.checked)}
              className="mt-0.5"
            />
            <span>我已阅读并同意《个人信息处理告知》，同意平台为处理本次申请收集并使用我的简历信息。</span>
          </label>
        )}
      </div>
    </Modal>
  );
}
