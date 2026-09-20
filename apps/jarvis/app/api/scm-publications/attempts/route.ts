import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function GET(request: Request) {
  const publicationId =
    new URL(request.url).searchParams.get('publicationId')?.trim() ?? '';
  if (!publicationId) {
    return Response.json(
      { detail: 'publicationId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }

  try {
    const response = await controlPlaneRequest(
      `/v1/scm-publications/${encodeURIComponent(publicationId)}/attempts`,
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
