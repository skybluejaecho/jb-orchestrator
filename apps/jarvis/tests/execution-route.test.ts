import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GET } from '@/app/api/execution/route';

describe('GET /api/execution', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('executionId가 없으면 upstream을 호출하지 않는다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(new Request('http://jarvis.test/api/execution'));

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('실행 상세와 산출물을 서버 token으로 함께 조회한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ id: 'execution-1', nodes: [] }))
      .mockResolvedValueOnce(Response.json([{ id: 'artifact-1' }]));
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request('http://jarvis.test/api/execution?executionId=execution-1'),
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      execution: { id: 'execution-1', nodes: [] },
      artifacts: [{ id: 'artifact-1' }],
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      'http://control-plane.test/v1/workflow-executions/execution-1',
      'http://control-plane.test/v1/workflow-executions/execution-1/artifacts',
    ]);
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init?.headers).get('Authorization')).toBe(
        'Bearer server-token',
      );
    }
  });
});
