import { CalendarClock, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Job } from '@/domain/models';
import { remainingTime } from '@/domain/jobStatus';
import { APPLICATION_STATUS_LABEL } from '@/domain/labels';
import { FieldTag, JobTypeTag } from './JobTypeTag';
import { JobStatusBadge } from '@/components/ui/StatusBadge';

export function JobCard({ job }: { job: Job }) {
  return (
    <Link
      to={`/jobs/${job.id}`}
      className="group flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 shadow-card transition-shadow hover:shadow-pop"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <JobTypeTag type={job.type} />
          <FieldTag field={job.field} />
        </div>
        <JobStatusBadge status={job.status} />
      </div>

      <h3 className="text-base font-semibold text-ink group-hover:text-primary">{job.title}</h3>
      <p className="line-clamp-2 text-sm leading-relaxed text-ink2">{job.description}</p>

      <div className="mt-auto flex items-center gap-4 text-sm text-ink2">
        <span className="flex items-center gap-1">
          <CalendarClock size={15} className="text-muted" />
          <span className="text-xs">剩余 {remainingTime(job.deadline)}</span>
        </span>
        <span className="flex items-center gap-1">
          <Users size={15} className="text-muted" />
          <span className="text-xs">招募 {job.recruitCount} 人</span>
        </span>
      </div>

      {job.myApplicationStatus && (
        <div className="rounded-md bg-primary-soft px-3 py-1.5 text-xs text-primary">
          已申请 · {APPLICATION_STATUS_LABEL[job.myApplicationStatus]}
        </div>
      )}
    </Link>
  );
}
