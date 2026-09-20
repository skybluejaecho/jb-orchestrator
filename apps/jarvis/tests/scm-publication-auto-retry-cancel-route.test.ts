import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/scm-publications/automatic-retry/cancel/route';

describe('POST /api/scm-publications/automatic-retry/cancel', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('publication ID를 자동 재시도 취소 endpoint로 전달한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json(
          { id: 'publication/1', status: 'failed', next_attempt_at: null },
          { status: 202 },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      new Request(
        'http://jarvis.test/api/scm-publications/automatic-retry/cancel',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ publicationId: 'publication/1' }),
        },
      ),
    );

    expect(response.status).toBe(202);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/scm-publications/publication%2F1/automatic-retry/cancel',
    );
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer server-token',
    );
  });

  it('publication ID가 없으면 upstream을 호출하지 않는다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      new Request(
        'http://jarvis.test/api/scm-publications/automatic-retry/cancel',
        { method: 'POST', body: JSON.stringify({}) },
      ),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
