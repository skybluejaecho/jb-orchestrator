import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function GET(request: Request) {
  const projectId = new URL(request.url).searchParams.get('projectId');
  if (!projectId) {
    return Response.json(
      { detail: 'projectId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  const encodedId = encodeURIComponent(projectId);
  try {
    const [project, requests, workflows] = await Promise.all([
      controlPlaneRequest(`/v1/projects/${encodedId}`),
      controlPlaneRequest(`/v1/projects/${encodedId}/requests?limit=30`),
      controlPlaneRequest(
        `/v1/projects/${encodedId}/workflow-executions?limit=30`,
      ),
    ]);
    return Response.json({
      project: await project.json(),
      requests: await requests.json(),
      workflows: await workflows.json(),
    });
  } catch (error) {
    return proxyProblem(error);
  }
}
