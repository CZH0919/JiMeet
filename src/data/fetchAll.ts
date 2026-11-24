import type { Page } from '@/domain/models';
import { MAX_PAGE_SIZE } from '@/domain/models';

/**
 * 按后端每页上限循环拉取全部记录。
 *
 * 用于「一次性展示全部」的页面：既避免 page_size 超限（后端最大 50），
 * 也不会因只取第一页而静默截断数据。
 */
export async function fetchAllPages<T>(
  fetchPage: (page: number, pageSize: number) => Promise<Page<T>>,
): Promise<T[]> {
  const items: T[] = [];
  for (let page = 1; ; page += 1) {
    const result = await fetchPage(page, MAX_PAGE_SIZE);
    items.push(...result.items);
    if (items.length >= result.total || result.items.length === 0) break;
  }
  return items;
}
