import { useState } from 'react';
import type { Job } from '@/domain/models';
import { repo } from '@/data';
import { validateNote } from '@/domain/validation';
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
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState('');
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setFile(null);
    setNote('');
    setProgress(0);
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
    setUploading(true);
    try {
      const resume = await repo.files.uploadResume(file, setProgress);
      setSubmitting(true);
      const app = await repo.applications.submit({ jobId: job.id, resume, note });
      toast.success('申请提交成功，状态为「处理中」');
      reset();
      onSubmitted();
      onClose();
      void app;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '提交失败，请重试');
    } finally {
      setUploading(false);
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
          <Button variant="secondary" onClick={() => { reset(); onClose(); }}>
            取消
          </Button>
          <Button onClick={submit} loading={uploading || submitting} disabled={!file}>
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

        {uploading && (
          <div>
            <div className="mb-1 flex justify-between text-xs text-ink2">
              <span>上传中…</span>
              <span>{Math.round(progress * 100)}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-page">
              <div className="h-full bg-primary transition-all" style={{ width: `${progress * 100}%` }} />
            </div>
          </div>
        )}

        <Field label="补充说明（选填，可留空）" hint="请输入你的相关经验、技能或加入理由">
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="请输入"
            maxLength={500}
          />
          <div className="text-right text-xs text-muted">{note.length}/500</div>
        </Field>
      </div>
    </Modal>
  );
}
