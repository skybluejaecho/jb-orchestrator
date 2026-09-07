'use client';

import {
  AlertTriangle,
  BellPlus,
  LoaderCircle,
  Power,
  Save,
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
import { Input } from '@/components/ui/input';

const eventOptions = [
  { value: 'worker.readiness_alerted', label: 'Worker 배정 지연' },
  { value: 'worker.readiness_critical', label: 'Worker 긴급 경보' },
  { value: 'worker.readiness_resolved', label: 'Worker 경보 해소' },
] as const;

type NotificationSubscription = {
  id: string;
  provider_key: string;
  destination_ref: string;
  event_types: string[];
  enabled: boolean;
  updated_at: string;
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

function toggleEvent(current: string[], eventType: string): string[] {
  return current.includes(eventType)
    ? current.filter((value) => value !== eventType)
    : [...current, eventType];
}

export function NotificationSubscriptions({
  projectId,
  revision,
  onChanged,
}: {
  projectId: string;
  revision: number;
  onChanged: () => Promise<void> | void;
}) {
  const [subscriptions, setSubscriptions] = useState<
    NotificationSubscription[]
  >([]);
  const [draftEvents, setDraftEvents] = useState<Record<string, string[]>>({});
  const [providerKey, setProviderKey] = useState('webhook');
  const [destinationRef, setDestinationRef] = useState('');
  const [newEvents, setNewEvents] = useState<string[]>([
    'worker.readiness_critical',
    'worker.readiness_resolved',
  ]);
  const [creating, setCreating] = useState(false);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await readJson<NotificationSubscription[]>(
        await fetch(
          `/api/notification-subscriptions?projectId=${encodeURIComponent(projectId)}`,
        ),
      );
      setSubscriptions(result);
      setDraftEvents(
        Object.fromEntries(result.map((item) => [item.id, item.event_types])),
      );
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '알림 구독을 불러오지 못했습니다.',
      );
    }
  }, [projectId]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load, revision]);

  const create = async () => {
    if (!providerKey.trim() || !destinationRef.trim() || newEvents.length === 0)
      return;
    setCreating(true);
    setError(null);
    try {
      await readJson(
        await fetch('/api/notification-subscriptions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            projectId,
            providerKey,
            destinationRef,
            eventTypes: newEvents,
          }),
        }),
      );
      setDestinationRef('');
      await load();
      await onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '알림 구독을 등록하지 못했습니다.',
      );
    } finally {
      setCreating(false);
    }
  };

  const configure = async (
    subscription: NotificationSubscription,
    enabled: boolean,
  ) => {
    const eventTypes = draftEvents[subscription.id] ?? subscription.event_types;
    if (eventTypes.length === 0) return;
    setWorkingId(subscription.id);
    setError(null);
    try {
      await readJson(
        await fetch('/api/notification-subscriptions/configure', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            projectId,
            subscriptionId: subscription.id,
            eventTypes,
            enabled,
          }),
        }),
      );
      await load();
      await onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '알림 구독 설정을 변경하지 못했습니다.',
      );
    } finally {
      setWorkingId(null);
    }
  };

  return (
    <Card className="border border-white/7 bg-card/80 ring-0">
      <CardHeader className="border-b border-white/7 pb-4">
        <div className="flex items-center gap-2">
          <BellPlus aria-hidden="true" className="size-4 text-cyan-200" />
          <CardTitle>알림 구독</CardTitle>
        </div>
        <CardDescription>
          Provider 목적지 참조와 수신할 프로젝트 이벤트
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        {error && (
          <div className="flex gap-2 rounded-lg border border-red-300/15 bg-red-300/5 p-3 text-sm text-red-100">
            <AlertTriangle
              aria-hidden="true"
              className="mt-0.5 size-4 shrink-0"
            />
            {error}
          </div>
        )}

        <div className="space-y-3 rounded-lg border border-cyan-300/12 bg-cyan-300/4 p-3">
          <div className="grid gap-3 sm:grid-cols-[minmax(120px,0.4fr)_minmax(0,1fr)]">
            <Input
              aria-label="알림 Provider Key"
              value={providerKey}
              onChange={(event) => setProviderKey(event.target.value)}
              placeholder="webhook"
            />
            <Input
              aria-label="알림 목적지 참조"
              value={destinationRef}
              onChange={(event) => setDestinationRef(event.target.value)}
              placeholder="operations-primary"
            />
          </div>
          <p className="text-xs leading-5 text-white/35">
            목적지 참조는 Worker 환경에서 실제 URL과 Secret으로 해석되는
            불투명한 키입니다.
          </p>
          <div className="flex flex-wrap gap-3">
            {eventOptions.map((option) => (
              <label
                key={option.value}
                className="flex items-center gap-2 text-xs text-white/60"
              >
                <input
                  type="checkbox"
                  checked={newEvents.includes(option.value)}
                  onChange={() =>
                    setNewEvents((current) =>
                      toggleEvent(current, option.value),
                    )
                  }
                />
                {option.label}
              </label>
            ))}
            <Button
              type="button"
              size="sm"
              className="ml-auto"
              disabled={
                creating ||
                !providerKey.trim() ||
                !destinationRef.trim() ||
                newEvents.length === 0
              }
              onClick={() => void create()}
            >
              {creating && (
                <LoaderCircle aria-hidden="true" className="animate-spin" />
              )}
              구독 등록
            </Button>
          </div>
        </div>

        {subscriptions.length === 0 && (
          <p className="py-6 text-center text-sm text-white/35">
            등록된 알림 구독이 없습니다.
          </p>
        )}
        {subscriptions.map((subscription) => {
          const selected =
            draftEvents[subscription.id] ?? subscription.event_types;
          const changed =
            JSON.stringify([...selected].sort()) !==
            JSON.stringify([...subscription.event_types].sort());
          return (
            <div
              key={subscription.id}
              className="rounded-lg border border-white/7 bg-black/10 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">
                  {subscription.enabled ? '활성' : '중지'}
                </Badge>
                <span className="font-mono text-xs text-cyan-100/70">
                  {subscription.provider_key}
                </span>
                <span className="truncate text-sm text-white/70">
                  {subscription.destination_ref}
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  disabled={workingId === subscription.id}
                  onClick={() =>
                    void configure(subscription, !subscription.enabled)
                  }
                >
                  <Power aria-hidden="true" />
                  {subscription.enabled ? '중지' : '활성화'}
                </Button>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                {eventOptions.map((option) => (
                  <label
                    key={option.value}
                    className="flex items-center gap-2 text-xs text-white/55"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(option.value)}
                      onChange={() =>
                        setDraftEvents((current) => ({
                          ...current,
                          [subscription.id]: toggleEvent(
                            selected,
                            option.value,
                          ),
                        }))
                      }
                    />
                    {option.label}
                  </label>
                ))}
                {changed && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="ml-auto"
                    disabled={
                      workingId === subscription.id || selected.length === 0
                    }
                    onClick={() =>
                      void configure(subscription, subscription.enabled)
                    }
                  >
                    <Save aria-hidden="true" /> 필터 적용
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
