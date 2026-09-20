import { describe, expect, it } from 'vitest';

import {
  confirmsWorkspaceCleanup,
  hasReadyWorkspaceInspection,
} from '@/lib/workspace-confirmation';

describe('confirmsWorkspaceCleanup', () => {
  it('전체 외부 실행 UUID가 정확히 일치할 때만 승인한다', () => {
    const executionId = '11111111-2222-3333-4444-555555555555';

    expect(confirmsWorkspaceCleanup(executionId, executionId)).toBe(true);
    expect(confirmsWorkspaceCleanup(executionId, executionId.slice(0, 8))).toBe(
      false,
    );
    expect(confirmsWorkspaceCleanup(executionId, ` ${executionId}`)).toBe(
      false,
    );
  });
});

describe('hasReadyWorkspaceInspection', () => {
  const ready = {
    kind: 'inspect',
    status: 'succeeded',
    target_ref: 'develop',
    result: { clean: true, merged: true },
  };

  it('현재 ref의 clean·merged 검사만 정리 준비 상태로 인정한다', () => {
    expect(hasReadyWorkspaceInspection('develop', [ready])).toBe(true);
    expect(hasReadyWorkspaceInspection('main', [ready])).toBe(false);
    expect(
      hasReadyWorkspaceInspection('develop', [
        { ...ready, result: { clean: false, merged: true } },
      ]),
    ).toBe(false);
  });
});
