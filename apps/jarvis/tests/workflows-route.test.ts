import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GET } from '@/app/api/workflows/route';

describe('GET /api/workflows', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('project 범위의 워크플로 선택 목록을 proxy한다', async () => {
    const payload = {
      default: {
        definition_key: 'standard-delivery',
        definition_version: 1,
      },
      default_workflow: null,
      workflows: [{ id: 'workflow-1', key: 'planning-only', version: 1 }],
      available_skills: [],
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(payload));
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request('http://jarvis.test/api/workflows?projectId=project/1'),
    );

    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://control-plane.test/v1/projects/project%2F1/workflow-options',
    );
    await expect(response.json()).resolves.toEqual(payload);
  });

  it('projectId가 없으면 upstream을 호출하지 않는다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(new Request('http://jarvis.test/api/workflows'));

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
