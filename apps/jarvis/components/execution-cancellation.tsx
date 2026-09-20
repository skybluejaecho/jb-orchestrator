'use client';

import { AlertTriangle, Ban, X } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  cancellationPhrase,
  confirmsCancellation,
} from '@/lib/cancellation-confirmation';

type Problem = { detail?: string };

const cancellableStatuses = new Set([
  'pending',
  'running',
  'awaiting_approval',
]);

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as Problem;
    throw new Error(
      problem.detail ?? `요청에 실패했습니다. (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

export function ExecutionCancellation({
  executionId,
  status,
  onCancelled,
}: {
  executionId: string;
  status: string;
  onCancelled: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const phrase = cancellationPhrase(executionId);

  if (!cancellableStatuses.has(status)) return null;

  const close = () => {
    setOpen(false);
    setConfirmation('');
    setError(null);
  };

  const cancelExecution = async () => {
    if (!confirmsCancellation(executionId, confirmation)) return;
    setCancelling(true);
    setError(null);
    try {
      await readJson(
        await fetch('/api/cancellation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ executionId, confirmation }),
        }),
      );
      close();
      await onCancelled();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '실행을 취소하지 못했습니다.',
      );
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="border-t border-white/7 pt-4">
      {!open ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-medium text-white/75">실행 중단</p>
            <p className="mt-1 text-sm text-white/40">
              진행 중인 작업과 연결된 요청을 취소합니다.
            </p>
          </div>
          <Button
            type="button"
            variant="destructive"
            onClick={() => setOpen(true)}
          >
            <Ban aria-hidden="true" /> 실행 취소
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border border-red-300/20 bg-red-300/6 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle
              aria-hidden="true"
              className="mt-0.5 size-5 shrink-0 text-red-200"
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-red-50">
                    이 실행을 정말 취소할까요?
                  </p>
                  <p className="mt-1 text-sm leading-6 text-red-50/65">
                    활성 노드와 연결된 Run·Request가 종료되며, 실행 중인 외부
                    작업에도 취소가 전달됩니다. 이 작업은 되돌릴 수 없습니다.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label="취소 확인 닫기"
                  disabled={cancelling}
                  onClick={close}
                >
                  <X aria-hidden="true" />
                </Button>
              </div>

              <label
                htmlFor={`cancel-${executionId}`}
                className="mt-4 block text-sm text-red-50/75"
              >
                계속하려면 <strong className="font-mono">{phrase}</strong>를
                입력하세요.
              </label>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <Input
                  id={`cancel-${executionId}`}
                  value={confirmation}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={cancelling}
                  onChange={(event) => setConfirmation(event.target.value)}
                  className="font-mono"
                  placeholder={phrase}
                />
                <Button
                  type="button"
                  variant="destructive"
                  disabled={
                    cancelling ||
                    !confirmsCancellation(executionId, confirmation)
                  }
                  onClick={() => void cancelExecution()}
                >
                  {cancelling ? '취소 요청 중…' : '실행 취소 확정'}
                </Button>
              </div>
              {error && (
                <p role="alert" className="mt-3 text-sm text-red-100">
                  {error}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
