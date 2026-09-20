import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function GET() {
  try {
    const response = await controlPlaneRequest(
      '/v1/projects?status=active&limit=100',
    );
    return Response.json(await response.json());
  } catch (error) {
    return proxyProblem(error);
  }
}
