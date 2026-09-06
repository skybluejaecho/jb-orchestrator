import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/workflow-recommendations/route';

describe('POST /api/workflow-recommendations', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('요청 내용을 project 범위 추천 API로 전달한다', async () => {
    const payload = {
      id: 'recommendation-1',
      confidence: 'high',
      candidates: [],
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(payload));
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      new Request('http://jarvis.test/api/workflow-recommendations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: 'project/1', prompt: '기획해줘' }),
      }),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/projects/project%2F1/workflow-recommendations',
    );
    expect(init?.method).toBe('POST');
    if (typeof init?.body !== 'string')
      throw new Error('JSON body가 필요합니다.');
    expect(JSON.parse(init.body)).toEqual({
      prompt: '기획해줘',
      limit: 3,
    });
    await expect(response.json()).resolves.toEqual(payload);
  });

  it('빈 요청은 upstream 호출 전에 거부한다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      new Request('http://jarvis.test/api/workflow-recommendations', {
        method: 'POST',
        body: JSON.stringify({ projectId: 'project-1', prompt: ' ' }),
      }),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
