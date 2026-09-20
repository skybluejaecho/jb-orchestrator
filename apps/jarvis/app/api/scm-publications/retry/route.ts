import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function POST(request: Request) {
  let payload: { publicationId?: unknown };
  try {
    payload = (await request.json()) as { publicationId?: unknown };
  } catch {
    return Response.json(
      { detail: '올바른 JSON 요청 본문이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  const publicationId =
    typeof payload.publicationId === 'string'
      ? payload.publicationId.trim()
      : '';
  if (!publicationId) {
    return Response.json(
      { detail: 'publicationId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  try {
    const response = await controlPlaneRequest(
      `/v1/scm-publications/${encodeURIComponent(publicationId)}/retry`,
      { method: 'POST' },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
