import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PATCH } from '@/app/api/notification-subscriptions/configure/route';
import { GET, POST } from '@/app/api/notification-subscriptions/route';

function jsonRequest(url: string, method: string, body: unknown): Request {
  return new Request(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('Jarvis notification subscription routes', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('프로젝트 알림 구독을 서버 token으로 조회한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json([{ id: 'subscription-1' }]));
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request(
        'http://jarvis.test/api/notification-subscriptions?projectId=project%2F1',
      ),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/projects/project%2F1/notification-subscriptions',
    );
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer server-token',
    );
  });

  it('구독 등록 값을 Control Plane 계약으로 변환한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json({ id: 'subscription-1' }, { status: 201 }),
      );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      jsonRequest('http://jarvis.test/api/notification-subscriptions', 'POST', {
        projectId: 'project/1',
        providerKey: 'webhook',
        destinationRef: 'operations-primary',
        eventTypes: ['worker.readiness_critical', 'worker.readiness_resolved'],
      }),
    );

    expect(response.status).toBe(201);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/projects/project%2F1/notification-subscriptions',
    );
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({
      provider_key: 'webhook',
      destination_ref: 'operations-primary',
      event_types: ['worker.readiness_critical', 'worker.readiness_resolved'],
    });
  });

  it('이벤트 필터와 활성화 상태를 함께 변경한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ enabled: false }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await PATCH(
      jsonRequest(
        'http://jarvis.test/api/notification-subscriptions/configure',
        'PATCH',
        {
          projectId: 'project/1',
          subscriptionId: 'subscription/1',
          eventTypes: ['worker.readiness_critical'],
          enabled: false,
        },
      ),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/projects/project%2F1/notification-subscriptions/subscription%2F1',
    );
    expect(init?.method).toBe('PATCH');
    expect(JSON.parse(init?.body as string)).toEqual({
      event_types: ['worker.readiness_critical'],
      enabled: false,
    });
  });

  it('지원하지 않는 이벤트는 upstream 호출 전에 거부한다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      jsonRequest('http://jarvis.test/api/notification-subscriptions', 'POST', {
        projectId: 'project-1',
        providerKey: 'webhook',
        destinationRef: 'operations-primary',
        eventTypes: ['unsupported.event'],
      }),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
