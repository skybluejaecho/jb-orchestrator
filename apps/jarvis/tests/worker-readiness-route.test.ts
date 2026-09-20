import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GET } from '@/app/api/worker-readiness/route';

describe('GET /api/worker-readiness', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('프로젝트 범위 진단 endpoint를 호출한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ issues: [], coverage: [] }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request(
        'http://jarvis.test/api/worker-readiness?projectId=project%2F1',
      ),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/projects/project%2F1/worker-readiness',
    );
    expect(init?.method).toBeUndefined();
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer server-token',
    );
  });

  it('프로젝트 ID가 없으면 요청을 거절한다', async () => {
    const response = await GET(
      new Request('http://jarvis.test/api/worker-readiness'),
    );

    expect(response.status).toBe(400);
  });
});
