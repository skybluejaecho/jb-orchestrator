import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GET as getAttempts } from '@/app/api/notification-deliveries/attempts/route';
import { POST as cancelAutomaticRetry } from '@/app/api/notification-deliveries/automatic-retry/cancel/route';
import { POST as retryDelivery } from '@/app/api/notification-deliveries/retry/route';
import { GET as getDeliveries } from '@/app/api/notification-deliveries/route';

function commandRequest(url: string, body: unknown): Request {
  return new Request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('Jarvis notification delivery routes', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('프로젝트 알림 전송 목록을 서버 token으로 조회한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json([{ id: 'delivery-1' }]));
    vi.stubGlobal('fetch', fetchMock);

    const response = await getDeliveries(
      new Request(
        'http://jarvis.test/api/notification-deliveries?projectId=project%2F1',
      ),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/projects/project%2F1/notification-deliveries?limit=200',
    );
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer server-token',
    );
  });

  it('검증된 상태 필터를 Control Plane으로 전달한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json([]));
    vi.stubGlobal('fetch', fetchMock);

    const response = await getDeliveries(
      new Request(
        'http://jarvis.test/api/notification-deliveries?projectId=project-1&status=failed',
      ),
    );

    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://control-plane.test/v1/projects/project-1/notification-deliveries?limit=200&status=failed',
    );
  });

  it('지원하지 않는 상태 필터는 upstream 호출 전에 거부한다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await getDeliveries(
      new Request(
        'http://jarvis.test/api/notification-deliveries?projectId=project-1&status=unknown',
      ),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('프로젝트와 Delivery 범위를 유지해 Attempt를 조회한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json([]));
    vi.stubGlobal('fetch', fetchMock);

    const response = await getAttempts(
      new Request(
        'http://jarvis.test/api/notification-deliveries/attempts?projectId=project%2F1&deliveryId=delivery%2F1',
      ),
    );

    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://control-plane.test/v1/projects/project%2F1/notification-deliveries/delivery%2F1/attempts',
    );
  });

  it('수동 재시도 명령을 Control Plane으로 전달한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ status: 'pending' }, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await retryDelivery(
      commandRequest('http://jarvis.test/api/notification-deliveries/retry', {
        projectId: 'project/1',
        deliveryId: 'delivery/1',
      }),
    );

    expect(response.status).toBe(202);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/projects/project%2F1/notification-deliveries/delivery%2F1/retry',
    );
    expect(init?.method).toBe('POST');
  });

  it('자동 재시도 예약 취소 명령을 Control Plane으로 전달한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ status: 'failed' }, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await cancelAutomaticRetry(
      commandRequest(
        'http://jarvis.test/api/notification-deliveries/automatic-retry/cancel',
        { projectId: 'project/1', deliveryId: 'delivery/1' },
      ),
    );

    expect(response.status).toBe(202);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/projects/project%2F1/notification-deliveries/delivery%2F1/automatic-retry/cancel',
    );
    expect(init?.method).toBe('POST');
  });

  it('필수 식별자가 없으면 upstream 호출 전에 거부한다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await retryDelivery(
      commandRequest('http://jarvis.test/api/notification-deliveries/retry', {
        projectId: 'project-1',
      }),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
