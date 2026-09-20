import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

type ScmPublicationPayload = {
  externalExecutionId?: unknown;
  providerKey?: unknown;
  targetBranch?: unknown;
  title?: unknown;
  body?: unknown;
  idempotencyKey?: unknown;
};

function externalExecutionId(request: Request): string {
  return (
    new URL(request.url).searchParams.get('externalExecutionId')?.trim() ?? ''
  );
}

export async function GET(request: Request) {
  const executionId = externalExecutionId(request);
  if (!executionId) {
    return Response.json(
      { detail: 'externalExecutionId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  try {
    const response = await controlPlaneRequest(
      `/v1/external-executions/${encodeURIComponent(executionId)}/scm-publications`,
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}

export async function POST(request: Request) {
  let payload: ScmPublicationPayload;
  try {
    payload = (await request.json()) as ScmPublicationPayload;
  } catch {
    return Response.json(
      { detail: '올바른 JSON 요청 본문이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }

  const executionId =
    typeof payload.externalExecutionId === 'string'
      ? payload.externalExecutionId.trim()
      : '';
  const providerKey =
    typeof payload.providerKey === 'string' ? payload.providerKey.trim() : '';
  const targetBranch =
    typeof payload.targetBranch === 'string' ? payload.targetBranch.trim() : '';
  const title = typeof payload.title === 'string' ? payload.title.trim() : '';
  const body = typeof payload.body === 'string' ? payload.body.trim() : '';
  const idempotencyKey =
    typeof payload.idempotencyKey === 'string'
      ? payload.idempotencyKey.trim()
      : '';
  if (
    !executionId ||
    providerKey !== 'github' ||
    !targetBranch ||
    !title ||
    !idempotencyKey
  ) {
    return Response.json(
      {
        detail:
          '실행 ID, GitHub provider, 대상 브랜치, 제목과 멱등성 키가 필요합니다.',
        status: 400,
      },
      { status: 400 },
    );
  }

  try {
    const response = await controlPlaneRequest(
      `/v1/external-executions/${encodeURIComponent(executionId)}/scm-publications`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey,
        },
        body: JSON.stringify({
          provider_key: providerKey,
          target_branch: targetBranch,
          title,
          body,
        }),
      },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
