import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GET, POST } from '@/app/api/workspace-operations/route';

function operationRequest(body: unknown): Request {
  return new Request('http://jarvis.test/api/workspace-operations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('/api/workspace-operations', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('선택한 외부 실행의 작업 목록을 서버 token으로 조회한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json([{ id: 'operation-1' }]));
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request(
        'http://jarvis.test/api/workspace-operations?externalExecutionId=external%2F1',
      ),
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/external-executions/external%2F1/workspace-operations',
    );
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer server-token',
    );
  });

  it('검사 요청의 ref와 멱등성 키를 Control Plane으로 전달한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json(
          { id: 'operation-1', status: 'pending' },
          { status: 202 },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      operationRequest({
        externalExecutionId: 'external/1',
        kind: 'inspect',
        targetRef: 'develop',
        idempotencyKey: 'inspect-1',
      }),
    );

    expect(response.status).toBe(202);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://control-plane.test/v1/external-executions/external%2F1/workspace-operations',
    );
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('Idempotency-Key')).toBe('inspect-1');
    expect(typeof init?.body).toBe('string');
    expect(JSON.parse(init?.body as string)).toEqual({
      kind: 'inspect',
      target_ref: 'develop',
      confirmation: null,
    });
  });

  it('정확한 외부 실행 UUID가 없으면 정리 요청을 차단한다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      operationRequest({
        externalExecutionId: '11111111-2222-3333-4444-555555555555',
        kind: 'cleanup',
        targetRef: 'develop',
        confirmation: '11111111',
        idempotencyKey: 'cleanup-1',
      }),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('확인된 정리 요청만 전체 UUID와 함께 전달한다', async () => {
    const executionId = '11111111-2222-3333-4444-555555555555';
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json(
          { id: 'operation-2', status: 'pending' },
          { status: 202 },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      operationRequest({
        externalExecutionId: executionId,
        kind: 'cleanup',
        targetRef: 'develop',
        confirmation: executionId,
        idempotencyKey: 'cleanup-2',
      }),
    );

    expect(response.status).toBe(202);
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init?.body as string)).toEqual({
      kind: 'cleanup',
      target_ref: 'develop',
      confirmation: executionId,
    });
  });
});
