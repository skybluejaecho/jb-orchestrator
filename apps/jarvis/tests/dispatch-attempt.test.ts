import { describe, expect, it, vi } from 'vitest';

import {
  prepareDispatchAttempt,
  type DispatchInput,
} from '@/lib/dispatch-attempt';

const input: DispatchInput = {
  projectId: 'project-1',
  title: '작업 제목',
  prompt: '구현 요청',
  workflow: null,
};

const changedInputs: Array<[DispatchInput, string]> = [
  [{ ...input, projectId: 'project-2' }, 'project'],
  [{ ...input, title: '다른 제목' }, 'title'],
  [{ ...input, prompt: '다른 요청' }, 'prompt'],
  [
    {
      ...input,
      workflow: { definitionKey: 'planning-only', definitionVersion: 1 },
    },
    'workflow',
  ],
];

describe('prepareDispatchAttempt', () => {
  it('동일한 입력을 재시도하면 기존 멱등성 키를 유지한다', () => {
    const createId = vi.fn(() => 'first');
    const first = prepareDispatchAttempt(null, input, createId);
    const retried = prepareDispatchAttempt(first, { ...input }, createId);

    expect(retried).toBe(first);
    expect(retried.key).toBe('jarvis-first');
    expect(createId).toHaveBeenCalledOnce();
  });

  it.each(changedInputs)('%s 변경 시 새로운 키를 만든다', (changedInput) => {
    const createId = vi
      .fn<() => string>()
      .mockReturnValueOnce('first')
      .mockReturnValueOnce('second');
    const first = prepareDispatchAttempt(null, input, createId);
    const changed = prepareDispatchAttempt(first, changedInput, createId);

    expect(changed.key).toBe('jarvis-second');
    expect(createId).toHaveBeenCalledTimes(2);
  });
});
