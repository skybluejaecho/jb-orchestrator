'use client';

import {
  AlertTriangle,
  ExternalLink,
  GitPullRequestArrow,
  History,
  LoaderCircle,
  RotateCcw,
  Send,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useId, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { safeReviewUrl, terminalExternalStatuses } from '@/lib/scm-publication';

type ScmPublication = {
  id: string;
  provider_key: string;
  source_branch: string;
  target_branch: string;
  title: string;
  status: 'pending' | 'claimed' | 'succeeded' | 'failed';
  result: Record<string, unknown> | null;
  failure_reason: string | null;
  failure_code:
    | 'workspace_state'
    | 'provider_rejected'
    | 'provider_unavailable'
    | 'timeout'
    | 'result_mismatch'
    | 'unexpected'
    | null;
  failure_retryable: boolean | null;
  attempt_count: number;
  automatic_retry_limit: number;
  next_attempt_at: string | null;
  created_at: string;
};

type ScmPublicationAttempt = {
  id: string;
  attempt_number: number;
  trigger: 'initial' | 'manual' | 'automatic' | 'lease_recovery';
  worker_id: string;
  status: 'claimed' | 'succeeded' | 'failed';
  failure_reason: string | null;
  failure_code: ScmPublication['failure_code'];
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

function statusLabel(publication: ScmPublication): string {
  if (publication.status === 'pending') return '게시 대기';
  if (publication.status === 'claimed') return '게시 중';
  if (publication.status === 'failed') return '게시 실패';
  return 'PR 준비됨';
}

function statusClass(status: ScmPublication['status']): string {
  if (status === 'failed') return 'border-red-300/20 bg-red-300/8 text-red-100';
  if (status === 'succeeded')
    return 'border-emerald-300/20 bg-emerald-300/8 text-emerald-100';
  return 'border-cyan-300/20 bg-cyan-300/8 text-cyan-100';
}

function failureLabel(publication: ScmPublication): string | null {
  if (!publication.failure_code) return null;
  if (publication.next_attempt_at) return '자동 재시도 예약됨';
  if (
    publication.failure_retryable &&
    publication.automatic_retry_limit > 0 &&
    publication.attempt_count > publication.automatic_retry_limit
  )
    return '자동 재시도 한도 도달';
  if (publication.failure_retryable) return '수동 재시도 가능';
  if (publication.failure_code === 'workspace_state')
    return '작업공간 확인 필요';
  if (publication.failure_code === 'provider_rejected')
    return '공급자 요청 확인 필요';
  if (publication.failure_code === 'result_mismatch') return '결과 검증 실패';
  return '수동 확인 필요';
}

function attemptTriggerLabel(trigger: ScmPublicationAttempt['trigger']) {
  if (trigger === 'manual') return '수동 재시도';
  if (trigger === 'automatic') return '자동 재시도';
  if (trigger === 'lease_recovery') return '임대 만료 회수';
  return '최초 시도';
}

function attemptStatusLabel(status: ScmPublicationAttempt['status']) {
  if (status === 'succeeded') return '성공';
  if (status === 'failed') return '실패';
  return '진행 중';
}

export function ScmPublications({
  externalExecutionId,
  externalStatus,
  sourceBranch,
  releasedAt,
  defaultTargetBranch,
  defaultTitle,
  revision,
  onChanged,
}: {
  externalExecutionId: string;
  externalStatus: string;
  sourceBranch: string | null;
  releasedAt: string | null;
  defaultTargetBranch: string;
  defaultTitle: string;
  revision: number;
  onChanged: () => Promise<void> | void;
}) {
  const formId = useId();
  const [publications, setPublications] = useState<ScmPublication[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [targetBranch, setTargetBranch] = useState(defaultTargetBranch);
  const [title, setTitle] = useState(defaultTitle);
  const [body, setBody] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [cancellingRetryId, setCancellingRetryId] = useState<string | null>(
    null,
  );
  const [expandedAttemptId, setExpandedAttemptId] = useState<string | null>(
    null,
  );
  const [attemptsByPublication, setAttemptsByPublication] = useState<
    Record<string, ScmPublicationAttempt[]>
  >({});
  const [loadingAttemptsId, setLoadingAttemptsId] = useState<string | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!sourceBranch) return;
    try {
      const result = await readJson<ScmPublication[]>(
        await fetch(
          `/api/scm-publications?externalExecutionId=${encodeURIComponent(externalExecutionId)}`,
        ),
      );
      setPublications(result);
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '게시 이력을 불러오지 못했습니다.',
      );
    }
  }, [externalExecutionId, sourceBranch]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load, revision]);

  const submit = async () => {
    if (!targetBranch.trim() || !title.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await readJson(
        await fetch('/api/scm-publications', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            externalExecutionId,
            providerKey: 'github',
            targetBranch,
            title,
            body,
            idempotencyKey: crypto.randomUUID(),
          }),
        }),
      );
      setFormOpen(false);
      await load();
      await onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '게시 요청을 등록하지 못했습니다.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const retry = async (publicationId: string) => {
    setRetryingId(publicationId);
    setError(null);
    try {
      await readJson(
        await fetch('/api/scm-publications/retry', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ publicationId }),
        }),
      );
      await load();
      await onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '게시 재시도를 등록하지 못했습니다.',
      );
    } finally {
      setRetryingId(null);
    }
  };

  const cancelAutomaticRetry = async (publicationId: string) => {
    setCancellingRetryId(publicationId);
    setError(null);
    try {
      await readJson(
        await fetch('/api/scm-publications/automatic-retry/cancel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ publicationId }),
        }),
      );
      await load();
      await onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '자동 재시도 예약을 취소하지 못했습니다.',
      );
    } finally {
      setCancellingRetryId(null);
    }
  };

  const toggleAttempts = async (publicationId: string) => {
    if (expandedAttemptId === publicationId) {
      setExpandedAttemptId(null);
      return;
    }
    setExpandedAttemptId(publicationId);
    setLoadingAttemptsId(publicationId);
    setError(null);
    try {
      const attempts = await readJson<ScmPublicationAttempt[]>(
        await fetch(
          `/api/scm-publications/attempts?publicationId=${encodeURIComponent(publicationId)}`,
        ),
      );
      setAttemptsByPublication((current) => ({
        ...current,
        [publicationId]: attempts,
      }));
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '게시 시도 이력을 불러오지 못했습니다.',
      );
      setExpandedAttemptId(null);
    } finally {
      setLoadingAttemptsId(null);
    }
  };

  if (!sourceBranch) return null;
  const canPublish =
    terminalExternalStatuses.has(externalStatus) && !releasedAt;

  return (
    <div className="mt-3 space-y-3 border-t border-cyan-300/10 pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <GitPullRequestArrow
          aria-hidden="true"
          className="size-4 text-cyan-200"
        />
        <span className="text-xs font-medium text-white/60">GitHub 게시</span>
        <span className="font-mono text-xs text-white/35">{sourceBranch}</span>
        {canPublish && !formOpen && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="ml-auto"
            onClick={() => setFormOpen(true)}
          >
            <Send aria-hidden="true" /> PR 요청
          </Button>
        )}
      </div>

      {!canPublish && !releasedAt && (
        <p className="text-xs text-white/35">
          외부 실행이 종료된 뒤 게시를 요청할 수 있습니다.
        </p>
      )}
      {releasedAt && (
        <p className="text-xs text-white/35">
          정리된 worktree에서는 새 게시를 요청할 수 없습니다.
        </p>
      )}

      {formOpen && (
        <div className="space-y-3 rounded-lg border border-cyan-300/15 bg-cyan-300/4 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium">Pull Request 게시 요청</p>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label="게시 요청 닫기"
              disabled={submitting}
              onClick={() => setFormOpen(false)}
            >
              <X aria-hidden="true" />
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label
              htmlFor={`${formId}-source`}
              className="text-xs text-white/45"
            >
              게시 브랜치
              <Input
                id={`${formId}-source`}
                value={sourceBranch}
                readOnly
                className="mt-1 font-mono text-white/45"
              />
            </label>
            <label
              htmlFor={`${formId}-target`}
              className="text-xs text-white/45"
            >
              대상 브랜치
              <Input
                id={`${formId}-target`}
                value={targetBranch}
                disabled={submitting}
                className="mt-1 font-mono"
                onChange={(event) => setTargetBranch(event.target.value)}
              />
            </label>
          </div>
          <label
            htmlFor={`${formId}-title`}
            className="block text-xs text-white/45"
          >
            PR 제목
            <Input
              id={`${formId}-title`}
              value={title}
              disabled={submitting}
              className="mt-1"
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <label
            htmlFor={`${formId}-body`}
            className="block text-xs text-white/45"
          >
            PR 본문
            <Textarea
              id={`${formId}-body`}
              value={body}
              disabled={submitting}
              className="mt-1 min-h-24"
              placeholder="변경 내용과 검증 결과를 입력하세요."
              onChange={(event) => setBody(event.target.value)}
            />
          </label>
          <div className="flex justify-end">
            <Button
              type="button"
              size="sm"
              disabled={submitting || !targetBranch.trim() || !title.trim()}
              onClick={() => void submit()}
            >
              {submitting ? (
                <LoaderCircle aria-hidden="true" className="animate-spin" />
              ) : (
                <Send aria-hidden="true" />
              )}
              {submitting ? '등록 중…' : '게시 요청 등록'}
            </Button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="flex gap-2 text-xs text-red-100">
          <AlertTriangle aria-hidden="true" className="size-3.5 shrink-0" />
          {error}
        </p>
      )}

      {publications.length > 0 && (
        <div className="space-y-2">
          {publications.slice(0, 5).map((publication) => {
            const reviewUrl = safeReviewUrl(publication.result);
            const classifiedFailure = failureLabel(publication);
            return (
              <div
                key={publication.id}
                className="rounded-md border border-white/7 bg-black/15 p-2 text-xs"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="min-w-0 truncate text-white/65">
                    {publication.title}
                  </span>
                  <Badge
                    variant="outline"
                    className={statusClass(publication.status)}
                  >
                    {statusLabel(publication)}
                  </Badge>
                  <span className="ml-auto font-mono text-white/30">
                    {publication.source_branch} → {publication.target_branch}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <span className="font-mono text-white/30">
                    시도 {publication.attempt_count}회
                  </span>
                  {classifiedFailure && (
                    <Badge
                      variant="outline"
                      className={
                        publication.failure_retryable
                          ? 'border-amber-300/20 bg-amber-300/8 text-amber-100'
                          : 'border-white/10 bg-white/5 text-white/50'
                      }
                    >
                      {classifiedFailure}
                    </Badge>
                  )}
                  {publication.status === 'failed' && canPublish && (
                    <div className="ml-auto flex items-center gap-1.5">
                      {publication.next_attempt_at && (
                        <Button
                          type="button"
                          size="xs"
                          variant="ghost"
                          disabled={
                            retryingId !== null || cancellingRetryId !== null
                          }
                          onClick={() =>
                            void cancelAutomaticRetry(publication.id)
                          }
                        >
                          {cancellingRetryId === publication.id ? (
                            <LoaderCircle
                              aria-hidden="true"
                              className="animate-spin"
                            />
                          ) : (
                            <X aria-hidden="true" />
                          )}
                          예약 취소
                        </Button>
                      )}
                      <Button
                        type="button"
                        size="xs"
                        variant="outline"
                        disabled={
                          retryingId !== null || cancellingRetryId !== null
                        }
                        onClick={() => void retry(publication.id)}
                      >
                        {retryingId === publication.id ? (
                          <LoaderCircle
                            aria-hidden="true"
                            className="animate-spin"
                          />
                        ) : (
                          <RotateCcw aria-hidden="true" />
                        )}
                        {publication.next_attempt_at
                          ? '지금 재시도'
                          : '다시 시도'}
                      </Button>
                    </div>
                  )}
                </div>
                {publication.failure_reason && (
                  <p className="mt-1.5 text-red-100/80">
                    {publication.failure_reason}
                  </p>
                )}
                {publication.next_attempt_at && (
                  <p className="mt-1.5 text-amber-100/80">
                    자동 재시도 예정{' '}
                    {new Date(publication.next_attempt_at).toLocaleString(
                      'ko-KR',
                    )}{' '}
                    · 자동 재시도 최대 {publication.automatic_retry_limit}회
                  </p>
                )}
                {reviewUrl && (
                  <a
                    href={reviewUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1.5 inline-flex items-center gap-1 text-cyan-200 hover:text-cyan-100"
                  >
                    Pull Request 열기
                    <ExternalLink aria-hidden="true" className="size-3" />
                  </a>
                )}
                {publication.attempt_count > 0 && (
                  <div className="mt-2 border-t border-white/7 pt-2">
                    <Button
                      type="button"
                      size="xs"
                      variant="ghost"
                      disabled={loadingAttemptsId === publication.id}
                      onClick={() => void toggleAttempts(publication.id)}
                    >
                      {loadingAttemptsId === publication.id ? (
                        <LoaderCircle
                          aria-hidden="true"
                          className="animate-spin"
                        />
                      ) : (
                        <History aria-hidden="true" />
                      )}
                      {expandedAttemptId === publication.id
                        ? '시도 이력 닫기'
                        : '시도 이력'}
                    </Button>
                    {expandedAttemptId === publication.id &&
                      attemptsByPublication[publication.id] && (
                        <ol className="mt-2 space-y-2 border-l border-cyan-300/15 pl-3">
                          {attemptsByPublication[publication.id].map(
                            (attempt) => (
                              <li key={attempt.id} className="space-y-0.5">
                                <div className="flex flex-wrap gap-2 text-white/55">
                                  <span className="font-mono">
                                    #{attempt.attempt_number}
                                  </span>
                                  <span>
                                    {attemptTriggerLabel(attempt.trigger)}
                                  </span>
                                  <Badge
                                    variant="outline"
                                    className={statusClass(attempt.status)}
                                  >
                                    {attemptStatusLabel(attempt.status)}
                                  </Badge>
                                  <span className="font-mono text-white/30">
                                    {attempt.worker_id}
                                  </span>
                                </div>
                                <p className="text-white/30">
                                  {new Date(attempt.started_at).toLocaleString(
                                    'ko-KR',
                                  )}
                                  {attempt.finished_at &&
                                    ` → ${new Date(attempt.finished_at).toLocaleString('ko-KR')}`}
                                </p>
                                {attempt.failure_reason && (
                                  <p className="text-red-100/75">
                                    {attempt.failure_code
                                      ? `[${attempt.failure_code}] `
                                      : ''}
                                    {attempt.failure_reason}
                                  </p>
                                )}
                              </li>
                            ),
                          )}
                        </ol>
                      )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
