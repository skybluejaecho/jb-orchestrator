import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function GET(request: Request) {
  const projectId = new URL(request.url).searchParams.get('projectId')?.trim();
  if (!projectId) {
    return Response.json(
      { detail: 'projectId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  try {
    const response = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/workflow-options`,
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
