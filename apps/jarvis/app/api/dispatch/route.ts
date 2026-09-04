import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

type DispatchPayload = {
  projectId?: unknown;
  title?: unknown;
  prompt?: unknown;
  workflow?: unknown;
  skillAddons?: unknown;
};

type WorkflowSelection = {
  definitionKey: string;
  definitionVersion: number;
};

const workflowKeyPattern = /^[a-z0-9][a-z0-9._-]*$/;

type SkillAddon = {
  nodeKey: string;
  skills: { key: string; version: number }[];
};

function skillAddons(value: unknown): SkillAddon[] | undefined {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.length > 64) return undefined;
  const result: SkillAddon[] = [];
  const nodeKeys = new Set<string>();
  for (const item of value) {
    if (!item || typeof item !== 'object') return undefined;
    const candidate = item as Record<string, unknown>;
    const nodeKey =
      typeof candidate.nodeKey === 'string' ? candidate.nodeKey.trim() : '';
    if (
      !nodeKey ||
      nodeKey.length > 128 ||
      nodeKeys.has(nodeKey) ||
      !Array.isArray(candidate.skills) ||
      candidate.skills.length === 0 ||
      candidate.skills.length > 64
    ) {
      return undefined;
    }
    const skills = candidate.skills.flatMap((item) => {
      if (!item || typeof item !== 'object') return [];
      const skill = item as Record<string, unknown>;
      const key = typeof skill.key === 'string' ? skill.key.trim() : '';
      const version = skill.version;
      return key &&
        key.length <= 128 &&
        workflowKeyPattern.test(key) &&
        Number.isInteger(version) &&
        Number(version) >= 1
        ? [{ key, version: Number(version) }]
        : [];
    });
    if (skills.length !== candidate.skills.length) return undefined;
    nodeKeys.add(nodeKey);
    result.push({ nodeKey, skills });
  }
  return result;
}

function workflowSelection(
  value: unknown,
): WorkflowSelection | null | undefined {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'object') return undefined;
  const candidate = value as Record<string, unknown>;
  const definitionKey =
    typeof candidate.definitionKey === 'string'
      ? candidate.definitionKey.trim()
      : '';
  const definitionVersion = candidate.definitionVersion;
  if (
    !definitionKey ||
    definitionKey.length > 128 ||
    !workflowKeyPattern.test(definitionKey) ||
    !Number.isInteger(definitionVersion) ||
    Number(definitionVersion) < 1
  ) {
    return undefined;
  }
  return { definitionKey, definitionVersion: Number(definitionVersion) };
}

export async function POST(request: Request) {
  let payload: DispatchPayload;
  try {
    payload = (await request.json()) as DispatchPayload;
  } catch {
    return Response.json(
      { detail: '올바른 JSON 요청 본문이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }

  const projectId =
    typeof payload.projectId === 'string' ? payload.projectId.trim() : '';
  const title = typeof payload.title === 'string' ? payload.title.trim() : '';
  const prompt =
    typeof payload.prompt === 'string' ? payload.prompt.trim() : '';
  const idempotencyKey = request.headers.get('idempotency-key')?.trim() ?? '';
  const workflow = workflowSelection(payload.workflow);
  const addons = skillAddons(payload.skillAddons);

  if (!projectId || !prompt || !idempotencyKey) {
    return Response.json(
      {
        detail: 'projectId, prompt와 Idempotency-Key가 필요합니다.',
        status: 400,
      },
      { status: 400 },
    );
  }
  if (idempotencyKey.length > 128) {
    return Response.json(
      { detail: 'Idempotency-Key는 128자 이하여야 합니다.', status: 400 },
      { status: 400 },
    );
  }
  if (workflow === undefined) {
    return Response.json(
      { detail: '올바른 workflow key와 version이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  if (addons === undefined) {
    return Response.json(
      { detail: '올바른 노드별 Skill 추가 구성이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }

  try {
    const response = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/dispatches`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey,
          'X-JB-Ingress-Key': 'jarvis',
        },
        body: JSON.stringify({
          title: title || null,
          prompt,
          workflow: workflow
            ? {
                definition_key: workflow.definitionKey,
                definition_version: workflow.definitionVersion,
              }
            : null,
          skill_addons: addons.map((addon) => ({
            node_key: addon.nodeKey,
            skills: addon.skills,
          })),
        }),
      },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
