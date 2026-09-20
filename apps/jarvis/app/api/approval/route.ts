import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

type ApprovalPayload = {
  executionId?: unknown;
  nodeKey?: unknown;
  approved?: unknown;
};

export async function POST(request: Request) {
  let payload: ApprovalPayload;
  try {
    payload = (await request.json()) as ApprovalPayload;
  } catch {
    return Response.json(
      { detail: '올바른 JSON 요청 본문이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }

  const executionId =
    typeof payload.executionId === 'string' ? payload.executionId.trim() : '';
  const nodeKey =
    typeof payload.nodeKey === 'string' ? payload.nodeKey.trim() : '';
  if (!executionId || !nodeKey || typeof payload.approved !== 'boolean') {
    return Response.json(
      {
        detail: 'executionId, nodeKey와 approved(boolean)가 필요합니다.',
        status: 400,
      },
      { status: 400 },
    );
  }

  try {
    const response = await controlPlaneRequest(
      `/v1/workflow-executions/${encodeURIComponent(executionId)}/approvals/${encodeURIComponent(nodeKey)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: payload.approved }),
      },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
