export type NotificationWorkerState = {
  kind: string;
  capabilities: string[];
  observed_status: 'online' | 'stale' | 'stopped';
};

export function notificationProviderState(
  workers: NotificationWorkerState[],
  providerKey: string,
) {
  const supporting = workers.filter(
    (worker) =>
      worker.kind === 'notification' &&
      worker.capabilities.includes(providerKey),
  );
  if (supporting.some((worker) => worker.observed_status === 'online'))
    return { label: '전송 Worker 온라인', available: true };
  if (supporting.length > 0)
    return { label: '전송 Worker 응답 지연 또는 종료', available: false };
  return { label: '지원하는 전송 Worker 없음', available: false };
}

type DeliverySummary = {
  status: 'pending' | 'claimed' | 'succeeded' | 'failed';
  provider_key: string;
  event_type: string;
  next_attempt_at: string | null;
  created_at: string;
};

export function filterAndPrioritizeDeliveries<T extends DeliverySummary>(
  deliveries: T[],
  providerKey: string,
  eventType: string,
): T[] {
  const priority: Record<DeliverySummary['status'], number> = {
    failed: 0,
    claimed: 1,
    pending: 2,
    succeeded: 3,
  };
  return deliveries
    .filter(
      (item) =>
        (providerKey === 'all' || item.provider_key === providerKey) &&
        (eventType === 'all' || item.event_type === eventType),
    )
    .sort((left, right) => {
      const leftPriority = left.next_attempt_at ? -1 : priority[left.status];
      const rightPriority = right.next_attempt_at ? -1 : priority[right.status];
      return (
        leftPriority - rightPriority ||
        Date.parse(right.created_at) - Date.parse(left.created_at)
      );
    });
}
