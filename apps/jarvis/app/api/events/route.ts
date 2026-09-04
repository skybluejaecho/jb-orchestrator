import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function GET(request: Request) {
  const projectId = new URL(request.url).searchParams.get('projectId');
  if (!projectId) {
    return Response.json(
      { detail: 'projectId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  const lastEventId = request.headers.get('last-event-id');
  try {
    const upstream = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/events/stream`,
      {
        headers: lastEventId ? { 'Last-Event-ID': lastEventId } : undefined,
        signal: request.signal,
      },
    );
    return new Response(upstream.body, {
      headers: {
        'Cache-Control': 'no-cache, no-transform',
        'Content-Type': 'text/event-stream',
        Connection: 'keep-alive',
      },
    });
  } catch (error) {
    return proxyProblem(error);
  }
}
