import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function GET() {
  try {
    const response = await controlPlaneRequest('/v1/workers?limit=100');
    return Response.json(await response.json(), { status: response.status });
  } catch (error) {
    return proxyProblem(error);
  }
}
