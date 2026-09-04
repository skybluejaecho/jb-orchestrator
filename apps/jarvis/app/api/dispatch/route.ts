import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

type DispatchPayload = {
  projectId?: unknown;
  title?: unknown;
  prompt?: unknown;
};

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
        body: JSON.stringify({ title: title || null, prompt }),
      },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
