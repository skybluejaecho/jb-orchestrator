import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

type DeliveryCommand = { projectId?: unknown; deliveryId?: unknown };

export async function POST(request: Request) {
  let payload: DeliveryCommand;
  try {
    payload = (await request.json()) as DeliveryCommand;
  } catch {
    return Response.json(
      { detail: '올바른 JSON 요청 본문이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  const projectId =
    typeof payload.projectId === 'string' ? payload.projectId.trim() : '';
  const deliveryId =
    typeof payload.deliveryId === 'string' ? payload.deliveryId.trim() : '';
  if (!projectId || !deliveryId) {
    return Response.json(
      { detail: 'projectId와 deliveryId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  try {
    const response = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/notification-deliveries/${encodeURIComponent(deliveryId)}/retry`,
      { method: 'POST' },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
