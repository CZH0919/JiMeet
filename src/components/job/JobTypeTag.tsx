import { clsx } from 'clsx';
import type { JobType } from '@/domain/models';
import { JOB_TYPE_LABEL } from '@/domain/labels';

export function JobTypeTag({ type, className }: { type: JobType; className?: string }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        type === 'competition' ? 'bg-primary-soft text-primary' : 'bg-success-soft text-success',
        className,
      )}
    >
      {JOB_TYPE_LABEL[type]}
    </span>
  );
}

export function FieldTag({ field }: { field: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-muted-soft px-2.5 py-0.5 text-xs font-medium text-ink2">
      {field}
    </span>
  );
}
