export function cancellationPhrase(executionId: string): string {
  return `취소 ${executionId.slice(0, 8)}`;
}

export function confirmsCancellation(
  executionId: string,
  confirmation: string,
): boolean {
  return confirmation === cancellationPhrase(executionId);
}
