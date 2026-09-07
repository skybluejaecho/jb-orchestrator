import { describe, expect, it } from 'vitest';

import {
  filterAndPrioritizeDeliveries,
  notificationProviderState,
} from '@/lib/notification-operations';

describe('notification operations policy', () => {
  it('온라인 Notification Worker의 Provider 지원을 확인한다', () => {
    expect(
      notificationProviderState(
        [
          {
            kind: 'notification',
            capabilities: ['webhook'],
            observed_status: 'online',
          },
        ],
        'webhook',
      ),
    ).toEqual({ label: '전송 Worker 온라인', available: true });
  });

  it('stale 또는 없는 Provider 지원을 경고하되 구분한다', () => {
    const stale = notificationProviderState(
      [
        {
          kind: 'notification',
          capabilities: ['webhook'],
          observed_status: 'stale',
        },
      ],
      'webhook',
    );
    const missing = notificationProviderState([], 'webhook');

    expect(stale.available).toBe(false);
    expect(stale.label).toContain('응답 지연');
    expect(missing.available).toBe(false);
    expect(missing.label).toContain('없음');
  });

  it('Provider와 이벤트를 필터링하고 예약·실패 항목을 우선한다', () => {
    const deliveries = [
      {
        id: 'success',
        status: 'succeeded' as const,
        provider_key: 'webhook',
        event_type: 'worker.readiness_resolved',
        next_attempt_at: null,
        created_at: '2026-09-08T03:00:00Z',
      },
      {
        id: 'failed',
        status: 'failed' as const,
        provider_key: 'webhook',
        event_type: 'worker.readiness_critical',
        next_attempt_at: null,
        created_at: '2026-09-08T01:00:00Z',
      },
      {
        id: 'scheduled',
        status: 'failed' as const,
        provider_key: 'webhook',
        event_type: 'worker.readiness_critical',
        next_attempt_at: '2026-09-08T04:00:00Z',
        created_at: '2026-09-08T00:00:00Z',
      },
      {
        id: 'other-provider',
        status: 'failed' as const,
        provider_key: 'email',
        event_type: 'worker.readiness_critical',
        next_attempt_at: null,
        created_at: '2026-09-08T02:00:00Z',
      },
    ];

    expect(
      filterAndPrioritizeDeliveries(
        deliveries,
        'webhook',
        'worker.readiness_critical',
      ).map((item) => item.id),
    ).toEqual(['scheduled', 'failed']);
  });
});
