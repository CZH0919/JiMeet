import { useState } from 'react';
import type { Application } from '@/domain/models';
import { repo } from '@/data';
import { formatDateTime } from '@/domain/format';
import { LIMITS, validateNote } from '@/domain/validation';
import { FileUploader } from './FileUploader';
import { Button } from '@/components/ui/Button';
import { Field, Textarea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { toast } from '@/stores/toast';

interface Props {
  app: Application;
  open: boolean;
  onClose: () => void;
  onSubmitted: () => void;
}

/**
 * 修改本人处理中的申请：新版简历覆盖旧版、可改补充说明。
 * 修改后该申请在发布者界面出现「已修改」标注（小红点）直到查看，并向发布者推送通知。
 */
export function EditApplicationDialog({ app, open, onClose, onSubmitted }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState(app.note ?? '');
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setFile(null);
    setNote(app.note ?? '');
  };

  const submit = async () => {
    const noteErr = validateNote(note);
    if (noteErr) {
      toast.error(noteErr);
      return;
    }
    setBusy(true);
    try {
      await repo.applications.update(app.id, { resumeFile: file ?? undefined, note });
      toast.success('申请已修改，发布者将收到通知');
      reset();
      onSubmitted();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '修改失败，请重试');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="修改申请"
      description={`「${app.jobTitle}」· 最近更新 ${formatDateTime(app.updatedAt)}`}
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
          <Button onClick={submit} loading={busy}>
            保存修改
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <p className="rounded-md bg-page px-3.5 py-2.5 text-xs leading-relaxed text-ink2">
          新简历将替换旧版，发布者会看到「已修改」标记。
        </p>

        <Field label="更换简历文件（选填）" hint="不选择则沿用当前简历">
          <FileUploader value={file} onChange={setFile} />
        </Field>

        <Field label="补充说明（选填）" hint={`不超过 ${LIMITS.note} 字，留空即清空说明`}>
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
      </div>
    </Modal>
  );
}
