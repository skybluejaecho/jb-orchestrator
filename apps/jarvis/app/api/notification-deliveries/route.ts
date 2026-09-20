import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function GET(request: Request) {
  const parameters = new URL(request.url).searchParams;
  const projectId = parameters.get('projectId')?.trim() ?? '';
  const status = parameters.get('status')?.trim() ?? '';
  const allowedStatuses = new Set([
    'pending',
    'claimed',
    'succeeded',
    'failed',
  ]);
  if (!projectId) {
    return Response.json(
      { detail: 'projectId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  if (status && !allowedStatuses.has(status)) {
    return Response.json(
      { detail: '지원하지 않는 알림 전송 상태입니다.', status: 400 },
      { status: 400 },
    );
  }
  try {
    const query = new URLSearchParams({ limit: '200' });
    if (status) query.set('status', status);
    const response = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/notification-deliveries?${query}`,
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
