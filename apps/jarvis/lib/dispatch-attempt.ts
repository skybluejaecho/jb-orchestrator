export type DispatchInput = {
  projectId: string;
  title: string | null;
  prompt: string;
  workflow: {
    definitionKey: string;
    definitionVersion: number;
  } | null;
  skillAddons: {
    nodeKey: string;
    skills: { key: string; version: number }[];
  }[];
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
    input.workflow?.definitionKey ?? null,
    input.workflow?.definitionVersion ?? null,
    input.skillAddons,
  ]);
  if (current?.fingerprint === fingerprint) return current;
  return { fingerprint, key: `jarvis-${createId()}` };
}
