import type { ApplicationStatus } from './models';

export class DomainError extends Error {}

const TERMINAL: ApplicationStatus[] = ['accepted', 'rejected', 'withdrawn'];

export const isTerminal = (s: ApplicationStatus) => TERMINAL.includes(s);

export const canWithdraw = (s: ApplicationStatus) => s === 'pending';
export const canModify = (s: ApplicationStatus) => s === 'pending';
export const canMark = (s: ApplicationStatus) => s === 'pending';

export type MarkAction = 'accept' | 'hold' | 'reject';

export function transition(
  current: ApplicationStatus,
  action: MarkAction | 'withdraw',
): ApplicationStatus {
  if (isTerminal(current)) {
    throw new DomainError('该申请已进入终态，不可再变更');
  }
  switch (action) {
    case 'accept':
      return 'accepted';
    case 'reject':
      return 'rejected';
    case 'hold':
      return 'pending';
    case 'withdraw':
      return 'withdrawn';
  }
}
