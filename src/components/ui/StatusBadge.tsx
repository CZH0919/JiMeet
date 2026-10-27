import { clsx } from 'clsx';
import type { ApplicationStatus, JobStatus } from '@/domain/models';
import {
  APPLICATION_STATUS_LABEL,
  APPLICATION_STATUS_TONE,
  JOB_STATUS_LABEL,
  JOB_STATUS_TONE,
} from '@/domain/labels';

const toneClass: Record<string, string> = {
  primary: 'bg-primary-soft text-primary',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  muted: 'bg-muted-soft text-muted',
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        toneClass[JOB_STATUS_TONE[status]],
      )}
    >
      {JOB_STATUS_LABEL[status]}
    </span>
  );
}

export function ApplicationStatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        toneClass[APPLICATION_STATUS_TONE[status]],
      )}
    >
      {APPLICATION_STATUS_LABEL[status]}
    </span>
  );
}
