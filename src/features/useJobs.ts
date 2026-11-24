import { useMemo, useState } from 'react';
import type { JobStatus, JobType } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from './useAsync';

export type TypeFilter = 'all' | JobType;

interface JobListParams {
  type: TypeFilter;
  keyword: string;
  tagId?: number;
  status?: JobStatus;
  page: number;
  pageSize: number;
}

export function useJobList(scope: 'all' | 'mine' = 'all', pageSize = 9) {
  const [type, setType] = useState<TypeFilter>('all');
  const [keyword, setKeyword] = useState('');
  const [tagId, setTagId] = useState<number | undefined>(undefined);
  const [status, setStatus] = useState<JobStatus | undefined>(undefined);
  const [page, setPage] = useState(1);

  const params: JobListParams = useMemo(
    () => ({ type, keyword, tagId, status, page, pageSize }),
    [type, keyword, tagId, status, page, pageSize],
  );

  const result = useAsync(
    () => (scope === 'mine' ? repo.jobs.listMine(params) : repo.jobs.list(params)),
    [type, keyword, tagId, status, page, pageSize, scope],
  );

  return {
    type,
    setType,
    keyword,
    setKeyword,
    tagId,
    setTagId,
    status,
    setStatus,
    page,
    setPage,
    pageSize,
    ...result,
  };
}
