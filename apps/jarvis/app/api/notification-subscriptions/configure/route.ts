import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

const supportedEventTypes = new Set([
  'worker.readiness_alerted',
  'worker.readiness_critical',
  'worker.readiness_resolved',
]);

type ConfigurePayload = {
  projectId?: unknown;
  subscriptionId?: unknown;
  eventTypes?: unknown;
  enabled?: unknown;
};

export async function PATCH(request: Request) {
  let payload: ConfigurePayload;
  try {
    payload = (await request.json()) as ConfigurePayload;
  } catch {
    return Response.json(
      { detail: '올바른 JSON 요청 본문이 필요합니다.', status: 400 },
      { status: 400 },
    );
  }
  const projectId =
    typeof payload.projectId === 'string' ? payload.projectId.trim() : '';
  const subscriptionId =
    typeof payload.subscriptionId === 'string'
      ? payload.subscriptionId.trim()
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
    !subscriptionId ||
    typeof payload.enabled !== 'boolean' ||
    eventTypes.length === 0 ||
    eventTypes.length !== eventTypeCount
  ) {
    return Response.json(
      {
        detail: '구독 식별자, 지원 이벤트와 활성화 상태가 필요합니다.',
        status: 400,
      },
      { status: 400 },
    );
  }
  try {
    const response = await controlPlaneRequest(
      `/v1/projects/${encodeURIComponent(projectId)}/notification-subscriptions/${encodeURIComponent(subscriptionId)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_types: eventTypes,
          enabled: payload.enabled,
        }),
      },
    );
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
