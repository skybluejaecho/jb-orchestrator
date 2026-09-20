import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/cancellation/route';

function cancellationRequest(body: unknown): Request {
  return new Request('http://jarvis.test/api/cancellation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('POST /api/cancellation', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('실행별 확인 문구가 정확하지 않으면 upstream을 호출하지 않는다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      cancellationRequest({
        executionId: '12345678-abcd',
        confirmation: '취소 other',
      }),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('선택한 실행만 Control Plane 취소 API로 전달한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json({ id: 'execution-1', status: 'cancelled' }),
      );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      cancellationRequest({
        executionId: 'execution/1',
        confirmation: '취소 executio',
      }),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/workflow-executions/execution%2F1/cancel',
    );
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer server-token',
    );
    expect(init?.body).toBeUndefined();
  });

  it('종료 상태와 경합한 upstream 충돌을 그대로 전달한다', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          Response.json(
            { detail: 'terminal workflow cannot be cancelled' },
            { status: 409 },
          ),
        ),
    );

    const response = await POST(
      cancellationRequest({
        executionId: 'execution-1',
        confirmation: '취소 executio',
      }),
    );

    expect(response.status).toBe(409);
    await expect(response.json()).resolves.toMatchObject({
      detail: 'terminal workflow cannot be cancelled',
    });
  });
});
