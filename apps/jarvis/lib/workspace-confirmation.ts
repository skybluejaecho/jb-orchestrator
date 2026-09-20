export function confirmsWorkspaceCleanup(
  externalExecutionId: string,
  confirmation: string,
): boolean {
  return confirmation === externalExecutionId;
}

type InspectionRecord = {
  kind: string;
  status: string;
  target_ref: string;
  result: Record<string, unknown> | null;
};

export function hasReadyWorkspaceInspection(
  targetRef: string,
  operations: InspectionRecord[],
): boolean {
  const inspection = operations.find(
    (operation) =>
      operation.kind === 'inspect' &&
      operation.status === 'succeeded' &&
      operation.target_ref === targetRef.trim(),
  );
  return (
    inspection?.result?.clean === true && inspection.result.merged === true
  );
}
