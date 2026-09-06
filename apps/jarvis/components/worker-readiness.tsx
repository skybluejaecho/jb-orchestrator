'use client';

import { AlertTriangle, CircleCheck, LoaderCircle, Route } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

type CapabilityCoverage = {
  executor_key: string;
  online_worker_ids: string[];
  stale_worker_ids: string[];
  stopped_worker_ids: string[];
};

type ReadinessIssue = {
  workflow_execution_id: string;
  node_key: string;
  executor_key: string;
  ready_since: string;
  reason: 'no_capable_worker' | 'capable_workers_offline';
};

type WorkerReadiness = {
  checked_at: string;
  online_execution_workers: number;
  coverage: CapabilityCoverage[];
  issues: ReadinessIssue[];
  alerts: ReadinessAlert[];
};

type ReadinessAlert = ReadinessIssue & {
  id: string;
  status: 'active' | 'resolved';
  severity: 'warning' | 'critical' | 'resolved';
  age_seconds: number;
  recommended_action:
    | 'start_capable_worker'
    | 'restart_capable_worker'
    | 'none';
  first_detected_at: string;
  last_observed_at: string;
  resolved_at: string | null;
};

type Problem = { detail?: string };

async function readReadiness(response: Response): Promise<WorkerReadiness> {
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as Problem;
    throw new Error(problem.detail ?? '작업 배정 상태를 불러오지 못했습니다.');
  }
  return (await response.json()) as WorkerReadiness;
}

function issueLabel(reason: ReadinessIssue['reason']) {
  return reason === 'capable_workers_offline'
    ? '지원 Worker가 모두 오프라인입니다.'
    : '이 executor를 지원하는 Worker가 없습니다.';
}

function actionLabel(action: ReadinessAlert['recommended_action']) {
  if (action === 'none') return '추가 조치가 필요하지 않습니다.';
  return action === 'restart_capable_worker'
    ? '해당 capability의 Worker 프로세스와 연결 설정을 확인한 뒤 다시 시작하세요.'
    : '이 executor capability를 제공하는 실행 Worker를 설치하거나 시작하세요.';
}

function elapsedLabel(seconds: number) {
  if (seconds < 60) return `${seconds}초`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분`;
  return `${Math.floor(seconds / 3600)}시간`;
}

export function WorkerReadinessPanel({
  projectId,
  revision,
}: {
  projectId: string;
  revision: number;
}) {
  const [report, setReport] = useState<WorkerReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alerts = report?.alerts ?? [];

  const load = useCallback(async () => {
    try {
      setReport(
        await readReadiness(
          await fetch(
            `/api/worker-readiness?projectId=${encodeURIComponent(projectId)}`,
          ),
        ),
      );
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '작업 배정 상태를 불러오지 못했습니다.',
      );
    }
  }, [projectId]);

  useEffect(() => {
    queueMicrotask(() => void load());
    const timer = setInterval(() => void load(), 30_000);
    return () => clearInterval(timer);
  }, [load, revision]);

  return (
    <Card className="border border-white/7 bg-card/80 ring-0">
      <CardHeader className="border-b border-white/7 pb-4">
        <div className="flex items-center gap-2">
          <Route aria-hidden="true" className="size-4 text-cyan-200" />
          <CardTitle>작업 배정 진단</CardTitle>
        </div>
        <CardDescription>
          online 실행 Worker {report?.online_execution_workers ?? '—'} · 배정
          경보{' '}
          {report
            ? alerts.filter((alert) => alert.status === 'active').length
            : '—'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!report && !error && (
          <p className="flex items-center gap-2 py-5 text-sm text-white/40">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            READY 작업과 capability를 비교하고 있습니다.
          </p>
        )}
        {error && (
          <p role="alert" className="flex gap-2 py-3 text-sm text-amber-100">
            <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
            {error}
          </p>
        )}
        {report?.coverage.length === 0 && (
          <p className="py-4 text-sm text-white/35">
            현재 배정을 기다리는 READY 작업이 없습니다.
          </p>
        )}
        {report && report.coverage.length > 0 && report.issues.length === 0 && (
          <p className="flex items-center gap-2 rounded-lg border border-emerald-300/15 bg-emerald-300/5 p-3 text-sm text-emerald-100">
            <CircleCheck aria-hidden="true" className="size-4" />
            모든 READY 작업을 처리할 online Worker가 있습니다.
          </p>
        )}
        {report?.coverage.map((coverage) => (
          <div
            key={coverage.executor_key}
            className="rounded-lg border border-white/7 bg-black/10 p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm text-white/70">
                {coverage.executor_key}
              </span>
              <Badge
                variant="outline"
                className="border-emerald-300/20 bg-emerald-300/8 text-emerald-100"
              >
                online {coverage.online_worker_ids.length}
              </Badge>
              {(coverage.stale_worker_ids.length > 0 ||
                coverage.stopped_worker_ids.length > 0) && (
                <Badge
                  variant="outline"
                  className="border-amber-300/20 bg-amber-300/8 text-amber-100"
                >
                  offline{' '}
                  {coverage.stale_worker_ids.length +
                    coverage.stopped_worker_ids.length}
                </Badge>
              )}
            </div>
          </div>
        ))}
        {alerts
          .filter((alert) => alert.status === 'active')
          .map((alert) => (
            <div
              key={alert.id}
              className={`rounded-lg border p-3 ${
                alert.severity === 'critical'
                  ? 'border-red-300/25 bg-red-300/8'
                  : 'border-amber-300/20 bg-amber-300/6'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <AlertTriangle
                  aria-hidden="true"
                  className="size-4 text-red-200"
                />
                <span className="font-medium text-red-50">
                  {alert.node_key}
                </span>
                <span className="font-mono text-xs text-white/40">
                  {alert.executor_key}
                </span>
                <Badge
                  variant="outline"
                  className="border-red-300/20 text-red-100"
                >
                  {alert.severity === 'critical' ? '긴급' : '주의'} ·{' '}
                  {elapsedLabel(alert.age_seconds)}
                </Badge>
                <span className="ml-auto font-mono text-xs text-white/25">
                  {alert.workflow_execution_id.slice(0, 8)}
                </span>
              </div>
              <p className="mt-1.5 text-sm text-red-100/75">
                {issueLabel(alert.reason)}
              </p>
              <p className="mt-1 text-xs text-white/45">
                {actionLabel(alert.recommended_action)}
              </p>
              <p className="mt-1 text-xs text-white/30">
                최초 감지{' '}
                {new Date(alert.first_detected_at).toLocaleString('ko-KR')}
              </p>
            </div>
          ))}
        {alerts
          .filter((alert) => alert.status === 'resolved')
          .slice(0, 3)
          .map((alert) => (
            <div
              key={alert.id}
              className="rounded-lg border border-emerald-300/12 bg-emerald-300/4 p-3 text-sm text-emerald-100/65"
            >
              <CircleCheck aria-hidden="true" className="mr-2 inline size-4" />
              {alert.node_key} · {alert.executor_key} 배정 경보 해소
            </div>
          ))}
      </CardContent>
    </Card>
  );
}
