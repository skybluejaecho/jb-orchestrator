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

export function WorkerReadinessPanel({
  projectId,
  revision,
}: {
  projectId: string;
  revision: number;
}) {
  const [report, setReport] = useState<WorkerReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          문제 {report?.issues.length ?? '—'}
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
        {report?.issues.map((issue) => (
          <div
            key={`${issue.workflow_execution_id}:${issue.node_key}`}
            className="rounded-lg border border-red-300/15 bg-red-300/5 p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <AlertTriangle
                aria-hidden="true"
                className="size-4 text-red-200"
              />
              <span className="font-medium text-red-50">{issue.node_key}</span>
              <span className="font-mono text-xs text-white/40">
                {issue.executor_key}
              </span>
              <span className="ml-auto font-mono text-xs text-white/25">
                {issue.workflow_execution_id.slice(0, 8)}
              </span>
            </div>
            <p className="mt-1.5 text-sm text-red-100/75">
              {issueLabel(issue.reason)}
            </p>
            <p className="mt-1 text-xs text-white/30">
              READY 이후 {new Date(issue.ready_since).toLocaleString('ko-KR')}
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
