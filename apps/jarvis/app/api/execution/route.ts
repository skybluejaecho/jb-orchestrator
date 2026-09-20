import { controlPlaneRequest, proxyProblem } from '@/lib/control-plane';

export async function GET(request: Request) {
  const executionId = new URL(request.url).searchParams
    .get('executionId')
    ?.trim();
  if (!executionId) {
    return Response.json(
      { detail: 'executionId가 필요합니다.', status: 400 },
      { status: 400 },
    );
  }

  const encodedId = encodeURIComponent(executionId);
  try {
    const [execution, artifacts, externalExecutions] = await Promise.all([
      controlPlaneRequest(`/v1/workflow-executions/${encodedId}`),
      controlPlaneRequest(`/v1/workflow-executions/${encodedId}/artifacts`),
      controlPlaneRequest(
        `/v1/external-executions?workflow_execution_id=${encodedId}`,
      ),
    ]);
    return Response.json({
      execution: await execution.json(),
      artifacts: await artifacts.json(),
      external_executions: await externalExecutions.json(),
    });
  } catch (error) {
    return proxyProblem(error);
  }
}
