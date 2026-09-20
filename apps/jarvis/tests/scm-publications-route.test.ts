import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GET, POST } from '@/app/api/scm-publications/route';

function publicationRequest(body: unknown): Request {
  return new Request('http://jarvis.test/api/scm-publications', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('/api/scm-publications', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('선택한 외부 실행의 게시 이력을 서버 token으로 조회한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json([{ id: 'publication-1' }]));
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request(
        'http://jarvis.test/api/scm-publications?externalExecutionId=external%2F1',
      ),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/external-executions/external%2F1/scm-publications',
    );
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer server-token',
    );
  });

  it('GitHub 게시 요청을 provider-neutral API 계약으로 전달한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json(
          { id: 'publication-1', status: 'pending' },
          { status: 202 },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      publicationRequest({
        externalExecutionId: 'external/1',
        providerKey: 'github',
        targetBranch: 'develop',
        title: '기능 검토',
        body: '검증 완료',
        idempotencyKey: 'publication-1',
      }),
    );

    expect(response.status).toBe(202);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/external-executions/external%2F1/scm-publications',
    );
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('Idempotency-Key')).toBe(
      'publication-1',
    );
    expect(JSON.parse(init?.body as string)).toEqual({
      provider_key: 'github',
      target_branch: 'develop',
      title: '기능 검토',
      body: '검증 완료',
    });
  });

  it('지원하지 않는 provider는 upstream 호출 전에 거부한다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      publicationRequest({
        externalExecutionId: 'external-1',
        providerKey: 'gitlab',
        targetBranch: 'develop',
        title: '기능 검토',
        idempotencyKey: 'publication-1',
      }),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
