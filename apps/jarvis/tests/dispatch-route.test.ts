import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/dispatch/route';

function dispatchRequest(body: unknown, idempotencyKey?: string): Request {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  if (idempotencyKey) headers.set('Idempotency-Key', idempotencyKey);
  return new Request('http://jarvis.test/api/dispatch', {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
}

describe('POST /api/dispatch', () => {
  beforeEach(() => {
    process.env.JARVIS_CONTROL_PLANE_URL = 'http://control-plane.test';
    process.env.JARVIS_API_TOKEN = 'server-token';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.JARVIS_CONTROL_PLANE_URL;
    delete process.env.JARVIS_API_TOKEN;
  });

  it('필수 입력이 없으면 upstream을 호출하지 않는다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(dispatchRequest({}));

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('Control Plane 계약에 맞춰 안전한 header와 payload를 전달한다', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json(
        {
          request: { id: 'request-1', title: '제목', prompt: '작업 내용' },
          workflow: { id: 'workflow-1' },
          replayed: false,
        },
        { status: 201 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      dispatchRequest(
        { projectId: 'project-1', title: '  제목  ', prompt: '  작업 내용  ' },
        'jarvis-attempt-1',
      ),
    );

    expect(response.status).toBe(201);
    const [url, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(url).toBe(
      'http://control-plane.test/v1/projects/project-1/dispatches',
    );
    expect(init?.method).toBe('POST');
    expect(headers.get('Authorization')).toBe('Bearer server-token');
    expect(headers.get('Idempotency-Key')).toBe('jarvis-attempt-1');
    expect(headers.get('X-JB-Ingress-Key')).toBe('jarvis');
    if (typeof init?.body !== 'string')
      throw new Error('JSON body가 필요합니다.');
    expect(JSON.parse(init.body)).toEqual({
      title: '제목',
      prompt: '작업 내용',
      workflow: null,
      skill_addons: [],
    });
  });

  it('선택한 워크플로의 정확한 key와 version을 전달한다', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json(
        {
          request: { id: 'request-1', title: null, prompt: '기획 요청' },
          workflow: { id: 'workflow-1' },
          replayed: false,
        },
        { status: 201 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      dispatchRequest(
        {
          projectId: 'project-1',
          prompt: '기획 요청',
          workflow: {
            definitionKey: 'planning-only',
            definitionVersion: 2,
          },
        },
        'jarvis-selected-1',
      ),
    );

    expect(response.status).toBe(201);
    const [, init] = fetchMock.mock.calls[0];
    if (typeof init?.body !== 'string')
      throw new Error('JSON body가 필요합니다.');
    expect(JSON.parse(init.body).workflow).toEqual({
      definition_key: 'planning-only',
      definition_version: 2,
    });
  });

  it('불완전한 워크플로 선택은 upstream 전에 거부한다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      dispatchRequest(
        {
          projectId: 'project-1',
          prompt: '기획 요청',
          workflow: { definitionKey: 'planning-only' },
        },
        'jarvis-invalid-1',
      ),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('노드별 Skill 추가 구성을 Control Plane 계약으로 변환한다', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ replayed: false }, { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      dispatchRequest(
        {
          projectId: 'project-1',
          prompt: '보안 검토 요청',
          skillAddons: [
            {
              nodeKey: 'verify',
              skills: [{ key: 'security-review', version: 2 }],
            },
          ],
        },
        'jarvis-skill-addon-1',
      ),
    );

    expect(response.status).toBe(201);
    const [, init] = fetchMock.mock.calls[0];
    if (typeof init?.body !== 'string')
      throw new Error('JSON body가 필요합니다.');
    expect(JSON.parse(init.body).skill_addons).toEqual([
      {
        node_key: 'verify',
        skills: [{ key: 'security-review', version: 2 }],
      },
    ]);
  });

  it('잘못된 Skill 추가 구성은 upstream 전에 거부한다', async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      dispatchRequest(
        {
          projectId: 'project-1',
          prompt: '검토 요청',
          skillAddons: [{ nodeKey: 'verify', skills: [{ key: 'Invalid' }] }],
        },
        'jarvis-invalid-addon-1',
      ),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('upstream 충돌 상태를 클라이언트에 전달한다', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          Response.json(
            { detail: '멱등성 키가 다른 payload에 사용되었습니다.' },
            { status: 409 },
          ),
        ),
    );

    const response = await POST(
      dispatchRequest(
        { projectId: 'project-1', prompt: '작업 내용' },
        'jarvis-attempt-1',
      ),
    );

    expect(response.status).toBe(409);
    await expect(response.json()).resolves.toMatchObject({
      detail: '멱등성 키가 다른 payload에 사용되었습니다.',
    });
  });
});
