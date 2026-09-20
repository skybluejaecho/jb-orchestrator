import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';
import { confirmsWorkspaceCleanup } from '@/lib/workspace-confirmation';

type WorkspaceOperationPayload = {
  externalExecutionId?: unknown;
  kind?: unknown;
  targetRef?: unknown;
  confirmation?: unknown;
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
      `/v1/external-executions/${encodeURIComponent(executionId)}/workspace-operations`,
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}

export async function POST(request: Request) {
  let payload: WorkspaceOperationPayload;
  try {
    payload = (await request.json()) as WorkspaceOperationPayload;
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
  const kind =
    payload.kind === 'inspect' || payload.kind === 'cleanup'
      ? payload.kind
      : null;
  const targetRef =
    typeof payload.targetRef === 'string' ? payload.targetRef.trim() : '';
  const idempotencyKey =
    typeof payload.idempotencyKey === 'string'
      ? payload.idempotencyKey.trim()
      : '';
  const confirmation =
    typeof payload.confirmation === 'string' ? payload.confirmation : null;
  if (!executionId || !kind || !targetRef || !idempotencyKey) {
    return Response.json(
      {
        detail: '실행 ID, 명령, 대상 ref와 멱등성 키가 필요합니다.',
        status: 400,
      },
      { status: 400 },
    );
  }
  if (
    kind === 'cleanup' &&
    !confirmsWorkspaceCleanup(executionId, confirmation ?? '')
  ) {
    return Response.json(
      {
        detail: '정리하려면 외부 실행 UUID를 정확히 입력해야 합니다.',
        status: 400,
      },
      { status: 400 },
    );
  }

  try {
    const response = await controlPlaneRequest(
      `/v1/external-executions/${encodeURIComponent(executionId)}/workspace-operations`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey,
        },
        body: JSON.stringify({
          kind,
          target_ref: targetRef,
          confirmation: kind === 'cleanup' ? confirmation : null,
        }),
      },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
