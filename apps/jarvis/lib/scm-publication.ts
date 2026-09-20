export const terminalExternalStatuses = new Set([
  'succeeded',
  'failed',
  'cancelled',
]);

export function safeReviewUrl(
  result: Record<string, unknown> | null,
): string | null {
  const value = result?.review_url;
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.toString() : null;
  } catch {
    return null;
  }
}
