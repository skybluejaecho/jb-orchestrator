import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GET } from '@/app/api/scm-publications/attempts/route';

describe('GET /api/scm-publications/attempts', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('게시 ID를 인코딩해 제어 평면으로 전달한다', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ attempt_number: 1 }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request(
        'http://jarvis.test/api/scm-publications/attempts?publicationId=publication%2F1',
      ),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual([{ attempt_number: 1 }]);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      'http://control-plane.test/v1/scm-publications/publication%2F1/attempts',
    );
    expect(
      new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Authorization'),
    ).toBe('Bearer server-token');
  });

  it('게시 ID가 없으면 요청을 거절한다', async () => {
    const response = await GET(
      new Request('http://jarvis.test/api/scm-publications/attempts'),
    );

    expect(response.status).toBe(400);
  });
});
