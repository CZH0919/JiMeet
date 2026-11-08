import { useMemo, useState } from 'react';
import type { JobType } from '@/domain/models';
import { repo } from '@/data';
import { useAsync } from './useAsync';

export type TypeFilter = 'all' | JobType;

interface JobListParams {
  type: TypeFilter;
  keyword: string;
  page: number;
  pageSize: number;
}

export function useJobList(scope: 'all' | 'mine' = 'all', pageSize = 9) {
  const [type, setType] = useState<TypeFilter>('all');
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);

  const params: JobListParams = useMemo(
    () => ({ type, keyword, page, pageSize }),
    [type, keyword, page, pageSize],
  );

  const result = useAsync(
    () =>
      scope === 'mine'
        ? repo.jobs.listMine({ ...params, type: params.type })
        : repo.jobs.list({ ...params, type: params.type }),
    [type, keyword, page, pageSize, scope],
  );

  return {
    type,
    setType,
    keyword,
    setKeyword,
    page,
    setPage,
    pageSize,
    ...result,
  };
}
