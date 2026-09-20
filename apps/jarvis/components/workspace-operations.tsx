'use client';

import {
  AlertTriangle,
  CheckCircle2,
  GitBranch,
  LoaderCircle,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  confirmsWorkspaceCleanup,
  hasReadyWorkspaceInspection,
} from '@/lib/workspace-confirmation';

type WorkspaceOperation = {
  id: string;
  kind: 'inspect' | 'cleanup';
  target_ref: string;
  requested_by: string;
  status: 'pending' | 'claimed' | 'succeeded' | 'failed';
  worker_id: string | null;
  result: Record<string, unknown> | null;
  failure_reason: string | null;
  created_at: string;
  completed_at: string | null;
};

type Problem = { detail?: string };

const terminalExternalStatuses = new Set(['succeeded', 'failed', 'cancelled']);

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as Problem;
    throw new Error(
      problem.detail ?? `요청에 실패했습니다. (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

function operationLabel(operation: WorkspaceOperation): string {
  if (operation.status === 'pending') return '처리 대기';
  if (operation.status === 'claimed') return 'Worker 처리 중';
  if (operation.status === 'failed') return '실패';
  return operation.kind === 'cleanup' ? '정리 완료' : '검사 완료';
}

function operationBadgeClass(status: WorkspaceOperation['status']): string {
  if (status === 'failed') return 'border-red-300/20 bg-red-300/8 text-red-100';
  if (status === 'succeeded')
    return 'border-emerald-300/20 bg-emerald-300/8 text-emerald-100';
  return 'border-cyan-300/20 bg-cyan-300/8 text-cyan-100';
}

function resultSummary(result: Record<string, unknown> | null): string | null {
  if (!result) return null;
  if (result.status === 'already_released')
    return '이미 정리된 작업공간입니다.';
  if (result.status === 'released')
    return 'worktree와 로컬 브랜치를 정리했습니다.';
  if (typeof result.clean === 'boolean' && typeof result.merged === 'boolean') {
    return `변경 사항 ${result.clean ? '없음' : '있음'} · 대상 ref 병합 ${
      result.merged ? '완료' : '필요'
    }`;
  }
  return null;
}

export function WorkspaceOperations({
  externalExecutionId,
  externalStatus,
  workspaceScope,
  releasedAt,
  defaultTargetRef,
  revision,
  onChanged,
}: {
  externalExecutionId: string;
  externalStatus: string;
  workspaceScope: string | null;
  releasedAt: string | null;
  defaultTargetRef: string;
  revision: number;
  onChanged: () => Promise<void> | void;
}) {
  const [operations, setOperations] = useState<WorkspaceOperation[]>([]);
  const [targetRef, setTargetRef] = useState(defaultTargetRef);
  const [cleanupOpen, setCleanupOpen] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [submitting, setSubmitting] = useState<'inspect' | 'cleanup' | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceScope) return;
    try {
      const result = await readJson<WorkspaceOperation[]>(
        await fetch(
          `/api/workspace-operations?externalExecutionId=${encodeURIComponent(externalExecutionId)}`,
        ),
      );
      setOperations(result);
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '작업공간 작업 이력을 불러오지 못했습니다.',
      );
    }
  }, [externalExecutionId, workspaceScope]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load, revision]);

  const submit = async (kind: 'inspect' | 'cleanup') => {
    if (!targetRef.trim()) return;
    if (
      kind === 'cleanup' &&
      !confirmsWorkspaceCleanup(externalExecutionId, confirmation)
    )
      return;
    setSubmitting(kind);
    setError(null);
    try {
      await readJson(
        await fetch('/api/workspace-operations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            externalExecutionId,
            kind,
            targetRef,
            confirmation: kind === 'cleanup' ? confirmation : null,
            idempotencyKey: crypto.randomUUID(),
          }),
        }),
      );
      setCleanupOpen(false);
      setConfirmation('');
      await load();
      await onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '작업공간 명령을 등록하지 못했습니다.',
      );
    } finally {
      setSubmitting(null);
    }
  };

  if (!workspaceScope) {
    return (
      <p className="mt-3 rounded-md border border-amber-300/15 bg-amber-300/5 p-2 text-xs leading-5 text-amber-100/70">
        이 실행은 작업공간 큐 도입 전에 생성되었습니다. OpenClaw 직접 CLI로
        검사하거나 정리하세요.
      </p>
    );
  }

  const canInspect = !releasedAt;
  const reviewReady = hasReadyWorkspaceInspection(targetRef, operations);
  const canCleanup =
    !releasedAt && terminalExternalStatuses.has(externalStatus) && reviewReady;

  return (
    <div className="mt-3 space-y-3 border-t border-cyan-300/10 pt-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <label
          htmlFor={`workspace-target-${externalExecutionId}`}
          className="min-w-0 flex-1 text-xs text-white/45"
        >
          병합 대상 ref
          <span className="mt-1 flex items-center gap-2">
            <GitBranch aria-hidden="true" className="size-4 shrink-0" />
            <Input
              id={`workspace-target-${externalExecutionId}`}
              value={targetRef}
              disabled={Boolean(submitting) || Boolean(releasedAt)}
              onChange={(event) => setTargetRef(event.target.value)}
              className="font-mono"
              aria-label="병합 대상 ref"
            />
          </span>
        </label>
        <div className="flex items-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!canInspect || Boolean(submitting) || !targetRef.trim()}
            onClick={() => void submit('inspect')}
          >
            {submitting === 'inspect' ? (
              <LoaderCircle aria-hidden="true" className="animate-spin" />
            ) : (
              <Search aria-hidden="true" />
            )}
            검사 요청
          </Button>
          {canCleanup && !cleanupOpen && (
            <Button
              type="button"
              size="sm"
              variant="destructive"
              disabled={Boolean(submitting) || !targetRef.trim()}
              onClick={() => setCleanupOpen(true)}
            >
              <Trash2 aria-hidden="true" /> 정리 준비
            </Button>
          )}
        </div>
      </div>

      {!releasedAt && !terminalExternalStatuses.has(externalStatus) && (
        <p className="text-xs text-white/35">
          외부 실행이 종료된 뒤 worktree 정리를 요청할 수 있습니다.
        </p>
      )}
      {!releasedAt &&
        terminalExternalStatuses.has(externalStatus) &&
        !reviewReady && (
          <p className="text-xs text-amber-100/60">
            현재 대상 ref에 대해 변경 사항 없음과 병합 완료가 확인되면 정리할 수
            있습니다.
          </p>
        )}

      {cleanupOpen && (
        <div className="rounded-lg border border-red-300/20 bg-red-300/6 p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle
              aria-hidden="true"
              className="mt-0.5 size-4 shrink-0 text-red-200"
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-red-50">
                    worktree 정리 요청
                  </p>
                  <p className="mt-1 text-xs leading-5 text-red-50/60">
                    깨끗하고 대상 ref에 병합된 경우에만 worktree와 로컬 브랜치가
                    삭제됩니다. 계속하려면 아래 실행 UUID를 그대로 입력하세요.
                  </p>
                </div>
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label="작업공간 정리 닫기"
                  disabled={submitting === 'cleanup'}
                  onClick={() => {
                    setCleanupOpen(false);
                    setConfirmation('');
                  }}
                >
                  <X aria-hidden="true" />
                </Button>
              </div>
              <p className="mt-2 break-all font-mono text-xs text-red-100/70">
                {externalExecutionId}
              </p>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <Input
                  value={confirmation}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={submitting === 'cleanup'}
                  onChange={(event) => setConfirmation(event.target.value)}
                  className="font-mono"
                  aria-label="작업공간 정리 확인 UUID"
                  placeholder={externalExecutionId}
                />
                <Button
                  type="button"
                  variant="destructive"
                  disabled={
                    submitting === 'cleanup' ||
                    !confirmsWorkspaceCleanup(externalExecutionId, confirmation)
                  }
                  onClick={() => void submit('cleanup')}
                >
                  {submitting === 'cleanup' ? (
                    <LoaderCircle aria-hidden="true" className="animate-spin" />
                  ) : (
                    <Trash2 aria-hidden="true" />
                  )}
                  정리 요청 확정
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-xs text-red-100">
          {error}
        </p>
      )}

      {operations.length > 0 && (
        <div className="space-y-2">
          {operations.slice(0, 5).map((operation) => {
            const summary = resultSummary(operation.result);
            return (
              <div
                key={operation.id}
                className="rounded-md border border-white/7 bg-black/15 p-2 text-xs"
              >
                <div className="flex flex-wrap items-center gap-2">
                  {operation.status === 'succeeded' ? (
                    <CheckCircle2
                      aria-hidden="true"
                      className="size-3.5 text-emerald-200"
                    />
                  ) : operation.status === 'failed' ? (
                    <AlertTriangle
                      aria-hidden="true"
                      className="size-3.5 text-red-200"
                    />
                  ) : (
                    <LoaderCircle
                      aria-hidden="true"
                      className="size-3.5 animate-spin text-cyan-200"
                    />
                  )}
                  <span className="font-mono text-white/55">
                    {operation.kind}
                  </span>
                  <Badge
                    variant="outline"
                    className={operationBadgeClass(operation.status)}
                  >
                    {operationLabel(operation)}
                  </Badge>
                  <span className="ml-auto font-mono text-white/30">
                    {operation.target_ref}
                  </span>
                </div>
                {summary && <p className="mt-1.5 text-white/50">{summary}</p>}
                {operation.failure_reason && (
                  <p className="mt-1.5 text-red-100/80">
                    {operation.failure_reason}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
