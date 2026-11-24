import { clsx } from 'clsx';
import type { JobType, Tag } from '@/domain/models';
import { JOB_TYPE_LABEL, JOB_TYPE_TONE } from '@/domain/labels';

const TONE: Record<string, string> = {
  primary: 'bg-primary-soft text-primary',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
};

export function JobTypeTag({ type, className }: { type: JobType; className?: string }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        TONE[JOB_TYPE_TONE[type]],
        className,
      )}
    >
      {JOB_TYPE_LABEL[type]}
    </span>
  );
}

/** 领域标签 chip */
export function TagTag({ tag }: { tag: Tag }) {
  return (
    <span className="inline-flex items-center rounded-full border border-line bg-page px-2.5 py-0.5 text-xs text-ink2">
      {tag.name}
    </span>
  );
}
