import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

const supportedEventTypes = new Set([
  'worker.readiness_alerted',
  'worker.readiness_critical',
  'worker.readiness_resolved',
]);

type SubscriptionPayload = {
  projectId?: unknown;
  providerKey?: unknown;
  destinationRef?: unknown;
  eventTypes?: unknown;
};

export async function GET(request: Request) {
  const projectId =
    new URL(request.url).searchParams.get('projectId')?.trim() ?? '';
  if (!projectId) {
    return Response.json(
      { detail: 'projectId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  try {
    const response = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/notification-subscriptions`,
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}

export async function POST(request: Request) {
  let payload: SubscriptionPayload;
  try {
    payload = (await request.json()) as SubscriptionPayload;
  } catch {
    return Response.json(
      { detail: '올바른 JSON 요청 본문이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  const projectId =
    typeof payload.projectId === 'string' ? payload.projectId.trim() : '';
  const providerKey =
    typeof payload.providerKey === 'string' ? payload.providerKey.trim() : '';
  const destinationRef =
    typeof payload.destinationRef === 'string'
      ? payload.destinationRef.trim()
      : '';
  const eventTypeCount = Array.isArray(payload.eventTypes)
    ? payload.eventTypes.length
    : 0;
  const eventTypes = Array.isArray(payload.eventTypes)
    ? payload.eventTypes.filter(
        (value): value is string =>
          typeof value === 'string' && supportedEventTypes.has(value),
      )
    : [];
  if (
    !projectId ||
    !/^[a-z][a-z0-9._-]{0,63}$/.test(providerKey) ||
    !destinationRef ||
    eventTypes.length === 0 ||
    eventTypes.length !== eventTypeCount
  ) {
    return Response.json(
      {
        detail: '프로젝트, provider, 목적지 참조와 지원 이벤트가 필요합니다.',
        status: 400,
      },
      { status: 400 },
    );
  }
  try {
    const response = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/notification-subscriptions`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider_key: providerKey,
          destination_ref: destinationRef,
          event_types: eventTypes,
        }),
      },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
