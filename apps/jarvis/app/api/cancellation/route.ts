import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';
import { confirmsCancellation } from '@/lib/cancellation-confirmation';

type CancellationPayload = {
  executionId?: unknown;
  confirmation?: unknown;
};

export async function POST(request: Request) {
  let payload: CancellationPayload;
  try {
    payload = (await request.json()) as CancellationPayload;
  } catch {
    return Response.json(
      { detail: '올바른 JSON 요청 본문이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }

  const executionId =
    typeof payload.executionId === 'string' ? payload.executionId.trim() : '';
  const confirmation =
    typeof payload.confirmation === 'string' ? payload.confirmation : '';
  if (!executionId || !confirmsCancellation(executionId, confirmation)) {
    return Response.json(
      { detail: '실행 ID와 정확한 취소 확인 문구가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }

  try {
    const response = await controlPlaneRequest(
      `/v1/workflow-executions/${encodeURIComponent(executionId)}/cancel`,
      { method: 'POST' },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
