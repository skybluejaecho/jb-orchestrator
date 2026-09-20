import { describe, expect, it } from 'vitest';

import {
  cancellationPhrase,
  confirmsCancellation,
} from '@/lib/cancellation-confirmation';

describe('실행 취소 확인 문구', () => {
  it('실행 식별자를 포함한 확인 문구를 만든다', () => {
    expect(cancellationPhrase('12345678-abcd-efgh')).toBe('취소 12345678');
  });

  it('대소문자와 공백까지 정확히 일치해야 한다', () => {
    const executionId = 'abcdef12-3456-7890';

    expect(confirmsCancellation(executionId, '취소 abcdef12')).toBe(true);
    expect(confirmsCancellation(executionId, '취소 ABCDEF12')).toBe(false);
    expect(confirmsCancellation(executionId, ' 취소 abcdef12')).toBe(false);
    expect(confirmsCancellation(executionId, '취소 abcdef12 ')).toBe(false);
  });
});
