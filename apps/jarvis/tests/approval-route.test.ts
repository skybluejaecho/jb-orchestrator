import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/approval/route';

function approvalRequest(body: unknown): Request {
  return new Request('http://jarvis.test/api/approval', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('POST /api/approval', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('boolean 승인 결정이 없으면 upstream을 호출하지 않는다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      approvalRequest({ executionId: 'execution-1', nodeKey: 'review' }),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    [true, '승인'],
    [false, '반려'],
  ])('%s 결정을 Control Plane 계약으로 전달한다 (%s)', async (approved) => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json({ id: 'execution-1', status: 'running' }),
      );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      approvalRequest({
        executionId: 'execution/1',
        nodeKey: 'human review',
        approved,
      }),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/workflow-executions/execution%2F1/approvals/human%20review',
    );
    expect(init?.method).toBe('POST');
    const headers = new Headers(init?.headers);
    expect(headers.get('Authorization')).toBe('Bearer server-token');
    expect(headers.get('Content-Type')).toBe('application/json');
    if (typeof init?.body !== 'string')
      throw new Error('JSON body가 필요합니다.');
    expect(JSON.parse(init.body)).toEqual({ approved });
  });

  it('이미 처리된 승인 충돌을 그대로 전달한다', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          Response.json(
            { detail: 'node is not awaiting approval' },
            { status: 409 },
          ),
        ),
    );

    const response = await POST(
      approvalRequest({
        executionId: 'execution-1',
        nodeKey: 'review',
        approved: true,
      }),
    );

    expect(response.status).toBe(409);
    await expect(response.json()).resolves.toMatchObject({
      detail: 'node is not awaiting approval',
    });
  });
});
