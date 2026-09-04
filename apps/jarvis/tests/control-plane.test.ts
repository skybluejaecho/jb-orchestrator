import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ControlPlaneProxyError,
  controlPlaneRequest,
} from '@/lib/control-plane';

describe('controlPlaneRequest', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test/';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('서버 token으로 Authorization header를 강제한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await controlPlaneRequest('/v1/projects', {
      headers: { Authorization: 'Bearer browser-token' },
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://control-plane.test/v1/projects');
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer server-token',
    );
    expect(init?.cache).toBe('no-store');
  });

  it('upstream 오류 상태와 detail을 보존한다', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          Response.json({ detail: '권한 없음' }, { status: 403 }),
        ),
    );

    await expect(controlPlaneRequest('/v1/projects')).rejects.toMatchObject({
      message: '권한 없음',
      status: 403,
    });
  });

  it('환경 변수가 없으면 fail closed 한다', async () => {
    delete process.env.JARVIS_API_TOKEN;

    await expect(controlPlaneRequest('/v1/projects')).rejects.toEqual(
      expect.objectContaining<Partial<ControlPlaneProxyError>>({ status: 503 }),
    );
  });
});
