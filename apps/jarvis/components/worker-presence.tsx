'use client';

import { AlertTriangle, Cpu, LoaderCircle, Radio, Server } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

type WorkerPresence = {
  id: string;
  worker_id: string;
  kind: 'execution' | 'workspace' | 'scm';
  hostname: string;
  process_id: number;
  capabilities: string[];
  workspace_scope: string | null;
  observed_status: 'online' | 'stale' | 'stopped';
  started_at: string;
  last_seen_at: string;
  stopped_at: string | null;
};

type Problem = { detail?: string };

const kindLabel = {
  execution: '실행 Worker',
  workspace: 'Workspace Worker',
  scm: 'SCM Worker',
};

const statusLabel = {
  online: '온라인',
  stale: '응답 지연',
  stopped: '종료됨',
};

function statusClass(status: WorkerPresence['observed_status']) {
  if (status === 'online')
    return 'border-emerald-300/20 bg-emerald-300/8 text-emerald-100';
  if (status === 'stale')
    return 'border-amber-300/20 bg-amber-300/8 text-amber-100';
  return 'border-white/10 bg-white/5 text-white/45';
}

async function readWorkers(response: Response): Promise<WorkerPresence[]> {
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as Problem;
    throw new Error(problem.detail ?? 'Worker 현황을 불러오지 못했습니다.');
  }
  return (await response.json()) as WorkerPresence[];
}

export function WorkerPresencePanel({ revision }: { revision: number }) {
  const [workers, setWorkers] = useState<WorkerPresence[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setWorkers(await readWorkers(await fetch('/api/workers')));
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Worker 현황을 불러오지 못했습니다.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
    const timer = setInterval(() => void load(), 30_000);
    return () => clearInterval(timer);
  }, [load, revision]);

  const online = workers.filter(
    (worker) => worker.observed_status === 'online',
  ).length;
  const stale = workers.filter(
    (worker) => worker.observed_status === 'stale',
  ).length;

  return (
    <Card className="border border-white/7 bg-card/80 ring-0">
      <CardHeader className="border-b border-white/7 pb-4">
        <div className="flex items-center gap-2">
          <Server aria-hidden="true" className="size-4 text-cyan-200" />
          <CardTitle>Worker 현황</CardTitle>
        </div>
        <CardDescription>
          온라인 {online} · 응답 지연 {stale} · 최근 인스턴스 {workers.length}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading && (
          <p className="flex items-center gap-2 py-5 text-sm text-white/40">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            Worker 상태를 확인하고 있습니다.
          </p>
        )}
        {error && (
          <p role="alert" className="flex gap-2 py-3 text-sm text-amber-100">
            <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
            {error}
          </p>
        )}
        {!loading && !error && workers.length === 0 && (
          <p className="py-5 text-sm text-white/35">
            아직 등록된 Worker 인스턴스가 없습니다.
          </p>
        )}
        {workers.slice(0, 8).map((worker) => (
          <div
            key={worker.id}
            className="rounded-lg border border-white/7 bg-black/10 p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Cpu aria-hidden="true" className="size-4 text-cyan-200/70" />
              <span className="text-sm font-medium">
                {kindLabel[worker.kind]}
              </span>
              <Badge
                variant="outline"
                className={statusClass(worker.observed_status)}
              >
                <Radio aria-hidden="true" className="size-3" />
                {statusLabel[worker.observed_status]}
              </Badge>
              <span className="ml-auto font-mono text-xs text-white/30">
                {worker.hostname}:{worker.process_id}
              </span>
            </div>
            <p className="mt-1.5 truncate font-mono text-xs text-white/40">
              {worker.worker_id}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {worker.capabilities.map((capability) => (
                <Badge
                  key={capability}
                  variant="outline"
                  className="border-white/8 bg-white/3 text-white/45"
                >
                  {capability}
                </Badge>
              ))}
            </div>
            {worker.workspace_scope && (
              <p className="mt-2 truncate font-mono text-[11px] text-white/25">
                {worker.workspace_scope}
              </p>
            )}
            <p className="mt-2 text-xs text-white/30">
              마지막 신호{' '}
              {new Date(worker.last_seen_at).toLocaleString('ko-KR')}
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
