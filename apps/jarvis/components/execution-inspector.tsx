'use client';

import {
  AlertTriangle,
  Bot,
  Check,
  ChevronRight,
  FileJson,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

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
import { cn } from '@/lib/utils';
import { ExecutionCancellation } from '@/components/execution-cancellation';

type NodeExecution = {
  id: string;
  node_key: string;
  executor_key: string;
  status: string;
  visit_count: number;
  attempt_count: number;
  outcome: string | null;
  output: Record<string, unknown> | null;
  worker_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
};

type Execution = {
  id: string;
  run_id: string;
  definition_key: string;
  definition_version: number;
  request_context: { title: string | null; prompt: string } | null;
  status: string;
  nodes: NodeExecution[];
  failure_reason: string | null;
  updated_at: string;
};

type Artifact = {
  id: string;
  producer_node_key: string;
  visit_count: number;
  outcome: string;
  content: Record<string, unknown>;
  created_at: string;
};

type ExternalExecution = {
  id: string;
  node_key: string;
  executor_key: string;
  external_session_key: string;
  external_agent_id: string | null;
  workspace_path: string | null;
  workspace_branch: string | null;
  workspace_base_ref: string | null;
  external_run_id: string | null;
  status: string;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

type Detail = {
  execution: Execution;
  artifacts: Artifact[];
  external_executions: ExternalExecution[];
};
type Problem = { detail?: string };

const statusLabel: Record<string, string> = {
  awaiting_approval: '승인 대기',
  active: '실행 중',
  cancelled: '취소됨',
  failed: '실패',
  pending: '준비 중',
  prepared: '호출 준비',
  ready: '실행 준비',
  running: '실행 중',
  succeeded: '성공',
};

function badgeClass(status: string) {
  if (['failed', 'cancelled', 'rejected'].includes(status))
    return 'border-red-400/25 bg-red-400/10 text-red-200';
  if (status === 'awaiting_approval')
    return 'border-amber-300/25 bg-amber-300/10 text-amber-100';
  if (['succeeded', 'approved', 'success'].includes(status))
    return 'border-emerald-300/25 bg-emerald-300/10 text-emerald-100';
  return 'border-cyan-300/25 bg-cyan-300/10 text-cyan-100';
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={badgeClass(status)}>
      {statusLabel[status] ?? status}
    </Badge>
  );
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

export function ExecutionInspector({
  executionId,
  revision,
  onChanged,
  onClose,
}: {
  executionId: string;
  revision: number;
  onChanged: () => void;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<{
    nodeKey: string;
    approved: boolean;
  } | null>(null);
  const [resolving, setResolving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await readJson<Detail>(
        await fetch(
          `/api/execution?executionId=${encodeURIComponent(executionId)}`,
        ),
      );
      setDetail(result);
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '실행 상세를 불러오지 못했습니다.',
      );
    } finally {
      setLoading(false);
    }
  }, [executionId]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load, revision]);

  const resolveApproval = async () => {
    if (!confirming) return;
    setResolving(true);
    try {
      await readJson(
        await fetch('/api/approval', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ executionId, ...confirming }),
        }),
      );
      setConfirming(null);
      await load();
      onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '승인 결정을 반영하지 못했습니다.',
      );
    } finally {
      setResolving(false);
    }
  };

  return (
    <Card className="border border-cyan-300/12 bg-card/90 ring-0">
      <CardHeader className="border-b border-white/7 pb-4">
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck aria-hidden="true" className="size-4 text-cyan-200" />
          실행 상세
        </CardTitle>
        <CardDescription>
          노드 진행 상태, 외부 에이전트 세션, 실행 결과와 승인 대기 항목을
          확인합니다.
        </CardDescription>
        <CardAction className="flex gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="실행 상세 새로고침"
            onClick={() => void load()}
          >
            <RefreshCw aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="실행 상세 닫기"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-5">
        {loading && !detail && <Skeleton className="h-40 w-full bg-white/5" />}
        {error && (
          <div className="flex gap-2 rounded-lg border border-amber-300/20 bg-amber-300/6 p-3 text-amber-50">
            <AlertTriangle
              aria-hidden="true"
              className="mt-0.5 size-4 shrink-0"
            />
            <p>{error}</p>
          </div>
        )}
        {detail && (
          <>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <h3 className="text-lg font-semibold">
                    {detail.execution.definition_key}
                  </h3>
                  <StatusBadge status={detail.execution.status} />
                </div>
                <p className="font-mono text-xs text-white/35">
                  v{detail.execution.definition_version} · {detail.execution.id}
                </p>
                {detail.execution.request_context && (
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-white/60">
                    {detail.execution.request_context.title ||
                      detail.execution.request_context.prompt}
                  </p>
                )}
              </div>
              <p className="font-mono text-xs text-white/30">
                run {detail.execution.run_id.slice(0, 8)}
              </p>
            </div>

            {detail.execution.failure_reason && (
              <p className="rounded-lg border border-red-300/20 bg-red-300/6 p-3 text-sm text-red-100">
                {detail.execution.failure_reason}
              </p>
            )}

            <section aria-labelledby="runtime-heading">
              <h3
                id="runtime-heading"
                className="mb-2 flex items-center gap-2 text-sm font-medium text-white/70"
              >
                <Bot aria-hidden="true" className="size-4" /> 외부 런타임{' '}
                {detail.external_executions.length}
              </h3>
              {detail.external_executions.length === 0 ? (
                <p className="rounded-lg border border-dashed border-white/8 px-3 py-5 text-center text-sm text-white/35">
                  아직 외부 에이전트에 할당된 실행이 없습니다.
                </p>
              ) : (
                <div className="grid gap-2 lg:grid-cols-2">
                  {detail.external_executions.map((external) => (
                    <article
                      key={external.id}
                      className="min-w-0 rounded-lg border border-cyan-300/10 bg-cyan-300/3 p-3"
                    >
                      <div className="mb-3 flex flex-wrap items-center gap-2">
                        <span className="font-medium">{external.node_key}</span>
                        <span className="font-mono text-xs text-white/40">
                          {external.executor_key}
                        </span>
                        <StatusBadge status={external.status} />
                      </div>
                      <dl className="grid gap-2 text-xs sm:grid-cols-[5.5rem_minmax(0,1fr)]">
                        <dt className="text-white/35">에이전트</dt>
                        <dd className="truncate font-mono text-white/65">
                          {external.external_agent_id ?? '기본 에이전트'}
                        </dd>
                        <dt className="text-white/35">세션</dt>
                        <dd
                          className="truncate font-mono text-white/50"
                          title={external.external_session_key}
                        >
                          {external.external_session_key}
                        </dd>
                        <dt className="text-white/35">외부 run</dt>
                        <dd
                          className="truncate font-mono text-white/50"
                          title={external.external_run_id ?? undefined}
                        >
                          {external.external_run_id ?? '할당 대기'}
                        </dd>
                        {external.workspace_branch && (
                          <>
                            <dt className="text-white/35">브랜치</dt>
                            <dd
                              className="truncate font-mono text-white/50"
                              title={external.workspace_branch}
                            >
                              {external.workspace_branch}
                            </dd>
                            <dt className="text-white/35">기준 commit</dt>
                            <dd className="truncate font-mono text-white/50">
                              {external.workspace_base_ref}
                            </dd>
                            <dt className="text-white/35">worktree</dt>
                            <dd
                              className="truncate font-mono text-white/50"
                              title={external.workspace_path ?? undefined}
                            >
                              {external.workspace_path}
                            </dd>
                          </>
                        )}
                      </dl>
                      {external.failure_reason && (
                        <p className="mt-3 rounded-md border border-red-300/15 bg-red-300/5 p-2 text-xs text-red-100">
                          {external.failure_reason}
                        </p>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section aria-labelledby="node-heading">
              <h3
                id="node-heading"
                className="mb-2 text-sm font-medium text-white/70"
              >
                노드
              </h3>
              <div className="space-y-2">
                {detail.execution.nodes.map((node, index) => (
                  <div
                    key={node.id}
                    className="rounded-lg border border-white/7 bg-black/10 p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="grid size-6 place-items-center rounded-md bg-white/5 font-mono text-xs text-white/45">
                        {index + 1}
                      </span>
                      <span className="font-medium">{node.node_key}</span>
                      <ChevronRight
                        aria-hidden="true"
                        className="size-3 text-white/20"
                      />
                      <span className="font-mono text-xs text-white/40">
                        {node.executor_key}
                      </span>
                      <StatusBadge status={node.status} />
                      {node.outcome && <StatusBadge status={node.outcome} />}
                      <span className="ml-auto font-mono text-xs text-white/30">
                        방문 {node.visit_count} · 시도 {node.attempt_count}
                      </span>
                    </div>

                    {node.output && (
                      <pre className="mt-3 max-h-48 overflow-auto rounded-md bg-black/25 p-3 text-xs leading-5 text-white/55">
                        {JSON.stringify(node.output, null, 2)}
                      </pre>
                    )}

                    {node.status === 'awaiting_approval' && (
                      <div className="mt-3 border-t border-white/7 pt-3">
                        {confirming?.nodeKey !== node.node_key ? (
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="mr-auto text-sm text-amber-100/70">
                              이 결정은 다음 그래프 경로를 즉시 실행합니다.
                            </p>
                            <Button
                              size="sm"
                              onClick={() =>
                                setConfirming({
                                  nodeKey: node.node_key,
                                  approved: true,
                                })
                              }
                            >
                              <Check aria-hidden="true" /> 승인
                            </Button>
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() =>
                                setConfirming({
                                  nodeKey: node.node_key,
                                  approved: false,
                                })
                              }
                            >
                              <X aria-hidden="true" /> 반려
                            </Button>
                          </div>
                        ) : (
                          <div
                            className={cn(
                              'flex flex-wrap items-center gap-2 rounded-md border p-3',
                              confirming.approved
                                ? 'border-emerald-300/20 bg-emerald-300/5'
                                : 'border-red-300/20 bg-red-300/5',
                            )}
                          >
                            <p className="mr-auto text-sm">
                              <strong>
                                {confirming.approved ? '승인' : '반려'}
                              </strong>{' '}
                              결정을 확정할까요?
                            </p>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={resolving}
                              onClick={() => setConfirming(null)}
                            >
                              돌아가기
                            </Button>
                            <Button
                              variant={
                                confirming.approved ? 'default' : 'destructive'
                              }
                              size="sm"
                              disabled={resolving}
                              onClick={() => void resolveApproval()}
                            >
                              {resolving ? '반영 중…' : '결정 확정'}
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            <section aria-labelledby="artifact-heading">
              <h3
                id="artifact-heading"
                className="mb-2 flex items-center gap-2 text-sm font-medium text-white/70"
              >
                <FileJson aria-hidden="true" className="size-4" /> 산출물{' '}
                {detail.artifacts.length}
              </h3>
              {detail.artifacts.length === 0 ? (
                <p className="rounded-lg border border-dashed border-white/8 px-3 py-5 text-center text-sm text-white/35">
                  아직 생성된 산출물이 없습니다.
                </p>
              ) : (
                <div className="grid gap-2 lg:grid-cols-2">
                  {detail.artifacts.map((artifact) => (
                    <article
                      key={artifact.id}
                      className="min-w-0 rounded-lg border border-white/7 bg-black/10 p-3"
                    >
                      <div className="mb-2 flex items-center gap-2">
                        <span className="font-medium">
                          {artifact.producer_node_key}
                        </span>
                        <StatusBadge status={artifact.outcome} />
                        <span className="ml-auto font-mono text-xs text-white/30">
                          visit {artifact.visit_count}
                        </span>
                      </div>
                      <pre className="max-h-56 overflow-auto rounded-md bg-black/25 p-3 text-xs leading-5 text-white/55">
                        {JSON.stringify(artifact.content, null, 2)}
                      </pre>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <ExecutionCancellation
              executionId={detail.execution.id}
              status={detail.execution.status}
              onCancelled={async () => {
                await load();
                onChanged();
              }}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}
