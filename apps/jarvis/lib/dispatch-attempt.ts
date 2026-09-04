export type DispatchInput = {
  projectId: string;
  title: string | null;
  prompt: string;
};

export type DispatchAttempt = {
  fingerprint: string;
  key: string;
};

export function prepareDispatchAttempt(
  current: DispatchAttempt | null,
  input: DispatchInput,
  createId: () => string = () => crypto.randomUUID(),
): DispatchAttempt {
  const fingerprint = JSON.stringify([
    input.projectId,
    input.title,
    input.prompt,
  ]);
  if (current?.fingerprint === fingerprint) return current;
  return { fingerprint, key: `jarvis-${createId()}` };
}
