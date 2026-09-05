import { describe, expect, it } from 'vitest';

import { safeReviewUrl, terminalExternalStatuses } from '@/lib/scm-publication';

describe('SCM publication presentation policy', () => {
  it('HTTPS review URL만 외부 링크로 노출한다', () => {
    expect(
      safeReviewUrl({ review_url: 'https://github.com/example/repo/pull/1' }),
    ).toBe('https://github.com/example/repo/pull/1');
    expect(safeReviewUrl({ review_url: 'javascript:alert(1)' })).toBeNull();
    expect(
      safeReviewUrl({ review_url: 'http://github.com/repo/pull/1' }),
    ).toBeNull();
    expect(safeReviewUrl(null)).toBeNull();
  });

  it('종료된 외부 실행 상태를 명시적으로 제한한다', () => {
    expect(terminalExternalStatuses.has('succeeded')).toBe(true);
    expect(terminalExternalStatuses.has('failed')).toBe(true);
    expect(terminalExternalStatuses.has('cancelled')).toBe(true);
    expect(terminalExternalStatuses.has('active')).toBe(false);
  });
});
