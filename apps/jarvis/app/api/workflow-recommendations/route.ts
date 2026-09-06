import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

type RecommendationPayload = {
  projectId?: unknown;
  prompt?: unknown;
};

export async function POST(request: Request) {
  let payload: RecommendationPayload;
  try {
    payload = (await request.json()) as RecommendationPayload;
  } catch {
    return Response.json(
      { detail: '올바른 JSON 요청 본문이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  const projectId =
    typeof payload.projectId === 'string' ? payload.projectId.trim() : '';
  const prompt =
    typeof payload.prompt === 'string' ? payload.prompt.trim() : '';
  if (!projectId || !prompt) {
    return Response.json(
      { detail: 'projectId와 prompt가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  try {
    const response = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/workflow-recommendations`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, limit: 3 }),
      },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
