import { describe, expect, it } from 'vitest';

import {
  isWorkflowDispatchBlocked,
  workflowCompatibilityGuidance,
} from '@/lib/workflow-compatibility';

describe('workflow compatibility', () => {
  it('호환되지 않는 워크플로의 dispatch를 차단한다', () => {
    expect(
      isWorkflowDispatchBlocked({
        compatible: false,
        compatibility_issues: [],
      }),
    ).toBe(true);
    expect(isWorkflowDispatchBlocked(undefined)).toBe(false);
  });

  it('OpenClaw workspace 제약을 사용자 조치와 함께 안내한다', () => {
    const guidance = workflowCompatibilityGuidance({
      code: 'openclaw.workspace_mode_unsupported',
      node_key: 'implement',
      executor_key: 'openclaw',
      message: 'upstream detail',
    });

    expect(guidance).toContain('Git worktree');
    expect(guidance).toContain('OpenClaw 에이전트');
  });
});
