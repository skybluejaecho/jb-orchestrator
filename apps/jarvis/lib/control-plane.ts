import 'server-only';

export class ControlPlaneProxyError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function configuration() {
  const baseUrl = process.env.JARVIS_CONTROL_PLANE_URL?.replace(/\/$/, '');
  const token = process.env.JARVIS_API_TOKEN;
  if (!baseUrl || !token) {
    throw new ControlPlaneProxyError(
      'Jarvis 연결 환경 변수가 설정되지 않았습니다.',
      503,
    );
  }
  return { baseUrl, token };
}

export async function controlPlaneRequest(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const { baseUrl, token } = configuration();
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    cache: 'no-store',
    headers,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const problem = (await response.json()) as { detail?: string };
      detail = problem.detail ?? detail;
    } catch {
      // Keep the HTTP status text when the upstream body is not JSON.
    }
    throw new ControlPlaneProxyError(detail, response.status);
  }
  return response;
}

export function proxyProblem(error: unknown): Response {
  const status = error instanceof ControlPlaneProxyError ? error.status : 502;
  const detail =
    error instanceof Error
      ? error.message
      : 'Control Plane에 연결할 수 없습니다.';
  return Response.json({ detail, status }, { status });
}
