'use client';

import {
  Activity,
  AlertTriangle,
  Boxes,
  CircleCheck,
  GitBranch,
  Radio,
  RefreshCw,
  ServerCog,
  type LucideIcon,
  Workflow,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import {
  RequestComposer,
  type DispatchResult,
} from '@/components/request-composer';
import { ExecutionInspector } from '@/components/execution-inspector';

type ConnectionState = 'connecting' | 'live' | 'degraded';

type Project = {
  id: string;
  key: string;
  name: string;
  repository_url: string;
  default_branch: string;
  status: string;
  updated_at: string;
};

type UserRequest = {
  id: string;
  title: string | null;
  prompt: string;
  status: string;
  updated_at: string;
  origin: { ingress_key: string } | null;
};

type NodeExecution = {
  node_key: string;
  status: string;
};

type WorkflowExecution = {
  id: string;
  run_id: string;
  definition_key: string;
  definition_version: number;
  status: string;
  nodes: NodeExecution[];
  updated_at: string;
};

type Overview = {
  project: Project;
  requests: UserRequest[];
  workflows: WorkflowExecution[];
};

type Problem = { detail?: string };

const eventTypes = [
  'request.created',
  'request.completed',
  'request.cancelled',
  'run.status_changed',
  'run.approved',
  'run.cancelled',
  'workflow.started',
  'workflow.node_started',
  'workflow.node_completed',
  'workflow.node_failed',
  'workflow.approval_resolved',
  'workflow.cancelled',
  'task.claimed',
  'task.completed',
  'task.failed',
  'task.lease_expired',
  'external_execution.prepared',
  'external_execution.accepted',
  'external_execution.finished',
  'budget.configured',
  'budget.limit_changed',
  'budget.reserved',
  'budget.released',
  'budget.settled',
  'budget.forfeited',
];

const statusLabel: Record<string, string> = {
  active: '진행 중',
  awaiting_approval: '승인 대기',
  cancelled: '취소됨',
  completed: '완료',
  failed: '실패',
  pending: '준비 중',
  queued: '대기',
  received: '접수',
  running: '실행 중',
  succeeded: '성공',
};

function statusClass(status: string) {
  if (['failed', 'cancelled'].includes(status)) {
    return 'border-red-400/25 bg-red-400/10 text-red-200';
  }
  if (status === 'awaiting_approval') {
    return 'border-amber-300/25 bg-amber-300/10 text-amber-100';
  }
  if (['succeeded', 'completed'].includes(status)) {
    return 'border-emerald-300/25 bg-emerald-300/10 text-emerald-100';
  }
  return 'border-cyan-300/25 bg-cyan-300/10 text-cyan-100';
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={statusClass(status)}>
      {statusLabel[status] ?? status}
    </Badge>
  );
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as Problem;
    throw new Error(
      problem.detail ?? `요청에 실패했습니다. (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

export function JarvisDashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    null,
  );
  const [overview, setOverview] = useState<Overview | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dispatchNotice, setDispatchNotice] = useState<{
    projectId: string;
    title: string;
  } | null>(null);
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(
    null,
  );
  const [eventRevision, setEventRevision] = useState(0);

  const loadProjects = useCallback(async () => {
    try {
      const result = await readJson<Project[]>(await fetch('/api/projects'));
      setProjects(result);
      setSelectedProjectId((current) => current ?? result[0]?.id ?? null);
      if (result.length === 0) setConnection('degraded');
    } catch (reason) {
      setConnection('degraded');
      setError(
        reason instanceof Error
          ? reason.message
          : '프로젝트를 불러오지 못했습니다.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const loadOverview = useCallback(async (projectId: string) => {
    try {
      const result = await readJson<Overview>(
        await fetch(`/api/overview?projectId=${encodeURIComponent(projectId)}`),
      );
      setOverview(result);
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '상태를 불러오지 못했습니다.',
      );
      setConnection('degraded');
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void loadProjects());
  }, [loadProjects]);

  useEffect(() => {
    if (!selectedProjectId) return;
    queueMicrotask(() => void loadOverview(selectedProjectId));
    const source = new EventSource(
      `/api/events?projectId=${encodeURIComponent(selectedProjectId)}`,
    );
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => {
        setEventRevision((current) => current + 1);
        void loadOverview(selectedProjectId);
      }, 180);
    };
    source.onopen = () => setConnection('live');
    source.onerror = () => setConnection('degraded');
    eventTypes.forEach((eventType) =>
      source.addEventListener(eventType, refresh),
    );
    return () => {
      clearTimeout(refreshTimer);
      source.close();
    };
  }, [loadOverview, selectedProjectId]);

  const metrics = useMemo(() => {
    const requests = overview?.requests ?? [];
    const workflows = overview?.workflows ?? [];
    return {
      active: requests.filter((item) =>
        ['active', 'received'].includes(item.status),
      ).length,
      running: workflows.filter((item) =>
        ['pending', 'running'].includes(item.status),
      ).length,
      approvals: workflows.filter(
        (item) =>
          item.status === 'awaiting_approval' ||
          item.nodes.some((node) => node.status === 'awaiting_approval'),
      ).length,
      failures: workflows.filter((item) => item.status === 'failed').length,
    };
  }, [overview]);

  const metricCards: Array<{
    label: string;
    value: number;
    icon: LucideIcon;
    color: string;
  }> = [
    {
      label: '활성 요청',
      value: metrics.active,
      icon: Activity,
      color: 'text-cyan-200',
    },
    {
      label: '실행 중',
      value: metrics.running,
      icon: Workflow,
      color: 'text-blue-200',
    },
    {
      label: '승인 대기',
      value: metrics.approvals,
      icon: Radio,
      color: 'text-amber-200',
    },
    {
      label: '실패',
      value: metrics.failures,
      icon: AlertTriangle,
      color: 'text-red-200',
    },
  ];

  const selectedProject =
    projects.find((project) => project.id === selectedProjectId) ?? null;

  const handleDispatched = (result: DispatchResult) => {
    if (!selectedProjectId) return;
    setDispatchNotice({
      projectId: selectedProjectId,
      title: result.request.title || result.request.prompt,
    });
    void loadOverview(selectedProjectId);
  };

  return (
    <main className="mx-auto min-h-screen max-w-[1600px] px-4 pb-10 pt-4 sm:px-6 lg:px-8">
      <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-white/8 pb-4">
        <div className="flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-200 shadow-[0_0_30px_oklch(0.78_0.135_203/12%)]">
            <ServerCog aria-hidden="true" className="size-5" />
          </div>
          <div>
            <p className="font-mono text-xs tracking-[0.18em] text-cyan-200/70">
              JARVIS
            </p>
            <h1 className="text-lg font-semibold tracking-tight">작업 관제</h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className={cn(
              'h-7 gap-1.5 border-white/10 bg-white/4 px-2.5',
              connection === 'live' ? 'text-emerald-200' : 'text-amber-100',
            )}
          >
            <Radio aria-hidden="true" className="size-3" />
            {connection === 'live'
              ? '실시간 연결'
              : connection === 'connecting'
                ? '연결 중'
                : '연결 확인 필요'}
          </Badge>
          <Button
            variant="outline"
            size="icon"
            aria-label="현재 상태 새로고침"
            onClick={() =>
              selectedProjectId && void loadOverview(selectedProjectId)
            }
            disabled={!selectedProjectId}
          >
            <RefreshCw aria-hidden="true" />
          </Button>
        </div>
      </header>

      <div className="grid gap-5 pt-5 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="rounded-xl border border-white/8 bg-black/10 p-3 lg:min-h-[calc(100vh-7rem)]">
          <div className="flex items-center gap-2 px-2 pb-3 pt-1 text-sm font-medium text-white/75">
            <Boxes aria-hidden="true" className="size-4 text-cyan-200" />
            프로젝트
            <span className="ml-auto font-mono text-xs text-white/40">
              {projects.length}
            </span>
          </div>
          <nav aria-label="프로젝트 목록" className="space-y-1">
            {loading &&
              Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-14 w-full bg-white/6" />
              ))}
            {!loading && projects.length === 0 && (
              <p className="rounded-lg border border-dashed border-white/10 px-3 py-5 text-sm leading-6 text-white/45">
                조회 가능한 프로젝트가 없습니다.
              </p>
            )}
            {projects.map((project) => (
              <button
                key={project.id}
                type="button"
                aria-label={`${project.name} 프로젝트 선택`}
                onClick={() => {
                  setSelectedProjectId(project.id);
                  setSelectedExecutionId(null);
                }}
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors',
                  selectedProjectId === project.id
                    ? 'border-cyan-300/20 bg-cyan-300/10 text-white'
                    : 'border-transparent text-white/60 hover:bg-white/5 hover:text-white/90',
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    'size-2 rounded-full',
                    selectedProjectId === project.id
                      ? 'bg-cyan-300'
                      : 'bg-white/25',
                  )}
                />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">
                    {project.name}
                  </span>
                  <span className="block truncate font-mono text-xs text-white/35">
                    {project.key}
                  </span>
                </span>
              </button>
            ))}
          </nav>
        </aside>

        <section className="min-w-0 space-y-5" aria-label="프로젝트 작업 현황">
          {dispatchNotice?.projectId === selectedProjectId && (
            <Card className="border border-emerald-300/20 bg-emerald-300/6 ring-0">
              <CardContent className="flex items-center gap-3 py-1 text-emerald-50">
                <CircleCheck
                  aria-hidden="true"
                  className="size-5 shrink-0 text-emerald-200"
                />
                <p className="min-w-0 truncate text-sm">
                  <span className="font-medium">요청을 등록했습니다.</span>{' '}
                  <span className="text-emerald-50/55">
                    {dispatchNotice.title}
                  </span>
                </p>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="ml-auto text-emerald-100/60 hover:text-emerald-50"
                  onClick={() => setDispatchNotice(null)}
                >
                  닫기
                </Button>
              </CardContent>
            </Card>
          )}
          {error && (
            <Card className="border border-amber-300/20 bg-amber-300/6 ring-0">
              <CardContent className="flex gap-3 py-1 text-amber-50">
                <AlertTriangle
                  aria-hidden="true"
                  className="mt-0.5 size-5 shrink-0"
                />
                <div>
                  <p className="font-medium">
                    Control Plane 연결을 확인해주세요.
                  </p>
                  <p className="mt-1 text-sm leading-6 text-amber-50/65">
                    {error}
                  </p>
                  <p className="mt-2 font-mono text-xs text-amber-50/45">
                    apps/jarvis/.env.local에 JARVIS_CONTROL_PLANE_URL과
                    JARVIS_API_TOKEN을 설정하세요.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p className="mb-1 font-mono text-xs tracking-[0.16em] text-cyan-200/60">
                {overview?.project.key ?? 'PROJECT OVERVIEW'}
              </p>
              <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                {overview?.project.name ?? '프로젝트를 선택하세요'}
              </h2>
            </div>
            {overview && (
              <div className="flex items-center gap-2 text-sm text-white/45">
                <GitBranch aria-hidden="true" className="size-4" />
                <span className="font-mono">
                  {overview.project.default_branch}
                </span>
              </div>
            )}
          </div>

          <RequestComposer
            project={selectedProject}
            onDispatched={handleDispatched}
          />

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {metricCards.map(({ label, value, icon: Icon, color }) => (
              <Card
                key={label}
                size="sm"
                className="border border-white/6 bg-card/85 ring-0"
              >
                <CardHeader>
                  <CardDescription>{label}</CardDescription>
                  <CardAction>
                    <Icon aria-hidden="true" className={cn('size-4', color)} />
                  </CardAction>
                  <CardTitle className="font-mono text-3xl font-semibold tabular-nums">
                    {overview ? value : '—'}
                  </CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(300px,0.75fr)]">
            <Card className="border border-white/7 bg-card/80 ring-0">
              <CardHeader className="border-b border-white/7 pb-4">
                <CardTitle>워크플로 실행</CardTitle>
                <CardDescription>최근 실행과 노드 진행 상태</CardDescription>
              </CardHeader>
              <CardContent className="px-2">
                <Table>
                  <TableHeader>
                    <TableRow className="border-white/7 hover:bg-transparent">
                      <TableHead className="text-white/40">워크플로</TableHead>
                      <TableHead className="text-white/40">상태</TableHead>
                      <TableHead className="text-white/40">노드</TableHead>
                      <TableHead className="text-right text-white/40">
                        업데이트
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {!overview && (
                      <TableRow className="border-white/7">
                        <TableCell
                          colSpan={4}
                          className="h-28 text-center text-white/35"
                        >
                          프로젝트 상태를 불러오는 중입니다.
                        </TableCell>
                      </TableRow>
                    )}
                    {overview?.workflows.length === 0 && (
                      <TableRow className="border-white/7">
                        <TableCell
                          colSpan={4}
                          className="h-28 text-center text-white/35"
                        >
                          아직 실행된 워크플로가 없습니다.
                        </TableCell>
                      </TableRow>
                    )}
                    {overview?.workflows.slice(0, 8).map((workflow) => {
                      const completed = workflow.nodes.filter((node) =>
                        ['succeeded', 'failed', 'cancelled'].includes(
                          node.status,
                        ),
                      ).length;
                      return (
                        <TableRow
                          key={workflow.id}
                          className="border-white/7 hover:bg-white/3"
                        >
                          <TableCell>
                            <button
                              type="button"
                              aria-label={`${workflow.definition_key} 실행 상세 보기`}
                              aria-pressed={selectedExecutionId === workflow.id}
                              onClick={() =>
                                setSelectedExecutionId(workflow.id)
                              }
                              className="rounded-md text-left outline-none hover:text-cyan-100 focus-visible:ring-2 focus-visible:ring-cyan-300/50"
                            >
                              <span className="block font-medium">
                                {workflow.definition_key}
                              </span>
                              <span className="block font-mono text-xs text-white/30">
                                v{workflow.definition_version} ·{' '}
                                {workflow.id.slice(0, 8)}
                              </span>
                            </button>
                          </TableCell>
                          <TableCell>
                            <StatusBadge status={workflow.status} />
                          </TableCell>
                          <TableCell className="font-mono text-white/60">
                            {completed}/{workflow.nodes.length}
                          </TableCell>
                          <TableCell className="text-right text-white/40">
                            {formatTime(workflow.updated_at)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card className="border border-white/7 bg-card/80 ring-0">
              <CardHeader className="border-b border-white/7 pb-4">
                <CardTitle>최근 요청</CardTitle>
                <CardDescription>사용자 요청의 현재 처리 상태</CardDescription>
              </CardHeader>
              <CardContent className="space-y-1 px-2">
                {!overview && <Skeleton className="h-24 w-full bg-white/5" />}
                {overview?.requests.length === 0 && (
                  <p className="px-3 py-10 text-center text-sm text-white/35">
                    아직 등록된 요청이 없습니다.
                  </p>
                )}
                {overview?.requests.slice(0, 7).map((request) => (
                  <div
                    key={request.id}
                    className="rounded-lg border border-transparent px-3 py-3 hover:border-white/6 hover:bg-white/3"
                  >
                    <div className="mb-1.5 flex items-center gap-2">
                      <StatusBadge status={request.status} />
                      <span className="ml-auto font-mono text-xs text-white/30">
                        {request.origin?.ingress_key ?? 'manual'}
                      </span>
                    </div>
                    <p className="truncate text-sm font-medium">
                      {request.title || request.prompt}
                    </p>
                    <p className="mt-1 text-xs text-white/35">
                      {formatTime(request.updated_at)}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          {selectedExecutionId && (
            <ExecutionInspector
              key={selectedExecutionId}
              executionId={selectedExecutionId}
              revision={eventRevision}
              onChanged={() =>
                selectedProjectId && void loadOverview(selectedProjectId)
              }
              onClose={() => setSelectedExecutionId(null)}
            />
          )}
        </section>
      </div>
    </main>
  );
}
