import { describe, expect, it } from 'vitest';

import {
  presentStructuredContent,
  summarizeExecutionProgress,
} from '../lib/execution-presentation';

describe('presentStructuredContent', () => {
  it('turns a structured phase result into readable fields', () => {
    expect(
      presentStructuredContent({
        summary: '기능을 구현했습니다.',
        changed_files: ['src/app.ts', 'tests/app.test.ts'],
        checks: ['테스트 통과'],
      }),
    ).toEqual({
      headline: '기능을 구현했습니다.',
      fields: [
        { label: '변경 파일', values: ['src/app.ts', 'tests/app.test.ts'] },
        { label: '확인한 항목', values: ['테스트 통과'] },
      ],
    });
  });

  it('supports nested outputs and verification verdicts', () => {
    expect(
      presentStructuredContent({
        output: { verdict: 'changes_requested', findings: ['검증 실패'] },
      }),
    ).toEqual({
      headline: '수정 필요',
      fields: [
        { label: '검증 판정', values: ['changes_requested'] },
        { label: '발견 사항', values: ['검증 실패'] },
      ],
    });
  });
});

describe('summarizeExecutionProgress', () => {
  it('shows the active node even when other nodes are complete', () => {
    expect(
      summarizeExecutionProgress('running', [
        { node_key: 'plan', status: 'succeeded' },
        { node_key: 'build', status: 'running' },
      ]),
    ).toEqual({
      message: 'build 단계를 실행하고 있습니다.',
      completed: 1,
      total: 2,
    });
  });

  it('prioritizes an approval gate', () => {
    expect(
      summarizeExecutionProgress('awaiting_approval', [
        { node_key: 'review', status: 'awaiting_approval' },
      ]).message,
    ).toBe('review 단계에서 승인을 기다리고 있습니다.');
  });

  it('reports terminal failures', () => {
    expect(
      summarizeExecutionProgress('failed', [
        { node_key: 'check', status: 'failed' },
        { node_key: 'cleanup', status: 'running' },
      ]),
    ).toEqual({
      message: '워크플로 실행이 실패했습니다.',
      completed: 1,
      total: 2,
    });
  });
});
