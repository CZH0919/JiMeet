import { CalendarClock, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Job } from '@/domain/models';
import { remainingTime } from '@/domain/format';
import { APPLICATION_STATUS_LABEL } from '@/domain/labels';
import { JobTypeTag, TagTag } from './JobTypeTag';
import { JobStatusBadge } from '@/components/ui/StatusBadge';

function headcountLabel(job: Job): string {
  return job.minHeadcount ? `${job.minHeadcount}–${job.maxHeadcount} 人` : `${job.maxHeadcount} 人`;
}

export function JobCard({ job }: { job: Job }) {
  return (
    <Link
      to={`/jobs/${job.id}`}
      className="group flex h-full flex-col gap-3 rounded-lg border border-line bg-surface p-5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-pop"
    >
      <div className="flex items-center justify-between gap-2">
        <JobTypeTag type={job.type} />
        <JobStatusBadge status={job.status} />
      </div>

      <h3 className="line-clamp-2 text-[15px] font-semibold leading-snug text-ink transition-colors group-hover:text-primary">
        {job.title}
      </h3>

      <div className="flex flex-wrap items-center gap-1.5">
        {job.tags.slice(0, 3).map((t) => (
          <TagTag key={t.id} tag={t} />
        ))}
      </div>

      <p className="text-xs text-ink2">
        发布者 {job.publisher.name}
      </p>

      <div className="mt-auto flex items-center justify-between border-t border-line pt-3 text-xs text-ink2">
        <span className="flex items-center gap-1">
          <CalendarClock size={14} className="text-muted" />
          剩余 {remainingTime(job.deadline)}
        </span>
        <span className="flex items-center gap-1">
          <Users size={14} className="text-muted" />
          {headcountLabel(job)}
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
