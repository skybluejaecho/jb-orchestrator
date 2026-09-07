'use client';

import {
  AlertTriangle,
  BellRing,
  History,
  LoaderCircle,
  RotateCcw,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { filterAndPrioritizeDeliveries } from '@/lib/notification-operations';

type DeliveryStatus = 'pending' | 'claimed' | 'succeeded' | 'failed';
type FailureCode =
  | 'provider_rejected'
  | 'provider_unavailable'
  | 'timeout'
  | 'lease_expired'
  | 'unexpected'
  | null;

type NotificationDelivery = {
  id: string;
  event_type: string;
  provider_key: string;
  destination_ref: string;
  status: DeliveryStatus;
  failure_reason: string | null;
  failure_code: FailureCode;
  failure_retryable: boolean | null;
  attempt_count: number;
  automatic_retry_limit: number;
  next_attempt_at: string | null;
  created_at: string;
};

type NotificationAttempt = {
  id: string;
  attempt_number: number;
  trigger: 'initial' | 'manual' | 'automatic' | 'lease_recovery';
  worker_id: string;
  status: 'claimed' | 'succeeded' | 'failed';
  failure_reason: string | null;
  failure_code: FailureCode;
  started_at: string;
  finished_at: string | null;
};

type Problem = { detail?: string };

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as Problem;
    throw new Error(
      problem.detail ?? `요청에 실패했습니다. (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

function statusLabel(status: DeliveryStatus) {
  if (status === 'pending') return '전송 대기';
  if (status === 'claimed') return '전송 중';
  if (status === 'failed') return '전송 실패';
  return '전송 성공';
}

function statusClass(status: DeliveryStatus) {
  if (status === 'failed') return 'border-red-300/20 bg-red-300/8 text-red-100';
  if (status === 'succeeded')
    return 'border-emerald-300/20 bg-emerald-300/8 text-emerald-100';
  return 'border-cyan-300/20 bg-cyan-300/8 text-cyan-100';
}

function attemptTriggerLabel(trigger: NotificationAttempt['trigger']) {
  if (trigger === 'manual') return '수동 재시도';
  if (trigger === 'automatic') return '자동 재시도';
  if (trigger === 'lease_recovery') return '임대 만료 회수';
  return '최초 시도';
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value));
}

export function NotificationDeliveries({
  projectId,
  revision,
  onChanged,
}: {
  projectId: string;
  revision: number;
  onChanged: () => Promise<void> | void;
}) {
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<
    Record<string, NotificationAttempt[]>
  >({});
  const [loadingAttemptsId, setLoadingAttemptsId] = useState<string | null>(
    null,
  );
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<DeliveryStatus | 'all'>(
    'all',
  );
  const [providerFilter, setProviderFilter] = useState('all');
  const [eventFilter, setEventFilter] = useState('all');

  const load = useCallback(async () => {
    try {
      const result = await readJson<NotificationDelivery[]>(
        await fetch(
          `/api/notification-deliveries?projectId=${encodeURIComponent(projectId)}${
            statusFilter === 'all' ? '' : `&status=${statusFilter}`
          }`,
        ),
      );
      setDeliveries(result);
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '알림 전송 이력을 불러오지 못했습니다.',
      );
    }
  }, [projectId, statusFilter]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load, revision]);

  const command = async (
    deliveryId: string,
    path: 'retry' | 'automatic-retry/cancel',
  ) => {
    setWorkingId(deliveryId);
    setError(null);
    try {
      await readJson(
        await fetch(`/api/notification-deliveries/${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ projectId, deliveryId }),
        }),
      );
      await load();
      await onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '알림 전송 상태를 변경하지 못했습니다.',
      );
    } finally {
      setWorkingId(null);
    }
  };

  const toggleAttempts = async (deliveryId: string) => {
    if (expandedId === deliveryId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(deliveryId);
    setLoadingAttemptsId(deliveryId);
    setError(null);
    try {
      const result = await readJson<NotificationAttempt[]>(
        await fetch(
          `/api/notification-deliveries/attempts?projectId=${encodeURIComponent(projectId)}&deliveryId=${encodeURIComponent(deliveryId)}`,
        ),
      );
      setAttempts((current) => ({ ...current, [deliveryId]: result }));
    } catch (reason) {
      setExpandedId(null);
      setError(
        reason instanceof Error
          ? reason.message
          : '알림 시도 이력을 불러오지 못했습니다.',
      );
    } finally {
      setLoadingAttemptsId(null);
    }
  };

  const providers = [
    ...new Set(deliveries.map((item) => item.provider_key)),
  ].sort();
  const eventTypes = [
    ...new Set(deliveries.map((item) => item.event_type)),
  ].sort();
  const visibleDeliveries = filterAndPrioritizeDeliveries(
    deliveries,
    providerFilter,
    eventFilter,
  );

  return (
    <Card className="border border-white/7 bg-card/80 ring-0">
      <CardHeader className="border-b border-white/7 pb-4">
        <div className="flex items-center gap-2">
          <BellRing aria-hidden="true" className="size-4 text-cyan-200" />
          <CardTitle>알림 전송</CardTitle>
        </div>
        <CardDescription>
          프로젝트 알림의 전송 상태와 재시도 이력 · {visibleDeliveries.length}건
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 pt-4">
        <div className="grid gap-2 sm:grid-cols-3">
          <select
            aria-label="알림 전송 상태 필터"
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as DeliveryStatus | 'all')
            }
            className="h-9 rounded-md border border-white/10 bg-black/20 px-3 text-xs text-white/70"
          >
            <option value="all">모든 상태</option>
            <option value="failed">실패</option>
            <option value="pending">대기</option>
            <option value="claimed">전송 중</option>
            <option value="succeeded">성공</option>
          </select>
          <select
            aria-label="알림 Provider 필터"
            value={providerFilter}
            onChange={(event) => setProviderFilter(event.target.value)}
            className="h-9 rounded-md border border-white/10 bg-black/20 px-3 text-xs text-white/70"
          >
            <option value="all">모든 Provider</option>
            {providers.map((provider) => (
              <option key={provider} value={provider}>
                {provider}
              </option>
            ))}
          </select>
          <select
            aria-label="알림 이벤트 필터"
            value={eventFilter}
            onChange={(event) => setEventFilter(event.target.value)}
            className="h-9 rounded-md border border-white/10 bg-black/20 px-3 text-xs text-white/70"
          >
            <option value="all">모든 이벤트</option>
            {eventTypes.map((eventType) => (
              <option key={eventType} value={eventType}>
                {eventType}
              </option>
            ))}
          </select>
        </div>
        {error && (
          <div className="flex gap-2 rounded-lg border border-red-300/15 bg-red-300/5 p-3 text-sm text-red-100">
            <AlertTriangle
              aria-hidden="true"
              className="mt-0.5 size-4 shrink-0"
            />
            {error}
          </div>
        )}
        {visibleDeliveries.length === 0 && !error && (
          <p className="py-8 text-center text-sm text-white/35">
            선택한 조건에 해당하는 알림 전송이 없습니다.
          </p>
        )}
        {visibleDeliveries.slice(0, 50).map((delivery) => (
          <div
            key={delivery.id}
            className="rounded-lg border border-white/7 bg-black/10 p-3"
          >
            <div className="flex flex-wrap items-start gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant="outline"
                    className={statusClass(delivery.status)}
                  >
                    {statusLabel(delivery.status)}
                  </Badge>
                  <span className="font-mono text-xs text-white/45">
                    {delivery.provider_key}
                  </span>
                  <span className="truncate text-xs text-white/35">
                    {delivery.destination_ref}
                  </span>
                </div>
                <p className="mt-2 truncate text-sm text-white/75">
                  {delivery.event_type}
                </p>
                <p className="mt-1 font-mono text-xs text-white/30">
                  {formatTime(delivery.created_at)} · 시도{' '}
                  {delivery.attempt_count}회
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={loadingAttemptsId === delivery.id}
                  onClick={() => void toggleAttempts(delivery.id)}
                >
                  {loadingAttemptsId === delivery.id ? (
                    <LoaderCircle aria-hidden="true" className="animate-spin" />
                  ) : (
                    <History aria-hidden="true" />
                  )}
                  이력
                </Button>
                {delivery.status === 'failed' && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={workingId === delivery.id}
                    onClick={() => void command(delivery.id, 'retry')}
                  >
                    <RotateCcw aria-hidden="true" /> 지금 재시도
                  </Button>
                )}
                {delivery.next_attempt_at && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={workingId === delivery.id}
                    onClick={() =>
                      void command(delivery.id, 'automatic-retry/cancel')
                    }
                  >
                    <X aria-hidden="true" /> 예약 취소
                  </Button>
                )}
              </div>
            </div>

            {delivery.failure_reason && (
              <p className="mt-3 rounded-md bg-red-300/5 px-3 py-2 text-xs leading-5 text-red-100/70">
                {delivery.failure_code ?? 'failure'} · {delivery.failure_reason}
              </p>
            )}
            {delivery.next_attempt_at && (
              <p className="mt-2 text-xs text-amber-100/70">
                {formatTime(delivery.next_attempt_at)} 자동 재시도 예정 · 최대{' '}
                {delivery.automatic_retry_limit}회
              </p>
            )}

            {expandedId === delivery.id && (
              <div className="mt-3 space-y-2 border-t border-white/7 pt-3">
                {(attempts[delivery.id] ?? []).length === 0 && (
                  <p className="text-xs text-white/35">시도 이력이 없습니다.</p>
                )}
                {(attempts[delivery.id] ?? []).map((attempt) => (
                  <div
                    key={attempt.id}
                    className="flex flex-wrap items-center gap-2 text-xs text-white/50"
                  >
                    <span className="font-mono">#{attempt.attempt_number}</span>
                    <span>{attemptTriggerLabel(attempt.trigger)}</span>
                    <Badge variant="outline" className="text-[10px]">
                      {attempt.status === 'claimed'
                        ? '진행 중'
                        : attempt.status === 'succeeded'
                          ? '성공'
                          : '실패'}
                    </Badge>
                    <span className="font-mono text-white/30">
                      {attempt.worker_id}
                    </span>
                    <span className="ml-auto">
                      {formatTime(attempt.started_at)}
                    </span>
                    {attempt.failure_reason && (
                      <span className="basis-full text-red-100/60">
                        {attempt.failure_reason}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
