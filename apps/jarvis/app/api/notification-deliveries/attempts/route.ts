import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function GET(request: Request) {
  const parameters = new URL(request.url).searchParams;
  const projectId = parameters.get('projectId')?.trim() ?? '';
  const deliveryId = parameters.get('deliveryId')?.trim() ?? '';
  if (!projectId || !deliveryId) {
    return Response.json(
      { detail: 'projectId와 deliveryId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  try {
    const response = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/notification-deliveries/${encodeURIComponent(deliveryId)}/attempts`,
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
