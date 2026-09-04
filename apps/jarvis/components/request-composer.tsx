'use client';

import { ArrowUpRight, LoaderCircle } from 'lucide-react';
import { useEffect, useRef, useState, type SyntheticEvent } from 'react';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import {
  prepareDispatchAttempt,
  type DispatchAttempt,
} from '@/lib/dispatch-attempt';

type ProjectSummary = {
  id: string;
  key: string;
  name: string;
};

type WorkflowOption = {
  id: string;
  key: string;
  version: number;
  entry_node: string;
  nodes: {
    key: string;
    kind: string;
    executor_key: string | null;
    phase_pack: { key: string; version: number } | null;
    skills: { key: string; version: number }[];
  }[];
  edges: {
    source: string;
    outcome: string;
    target: string;
    condition: { path: string; equals: unknown } | null;
  }[];
  phase_packs: {
    key: string;
    version: number;
    name: string;
    description: string;
    skills: { key: string; version: number }[];
  }[];
  skills: {
    key: string;
    version: number;
    name: string;
    description: string;
    source_kind: string;
  }[];
};

type WorkflowOptions = {
  default: {
    definition_key: string;
    definition_version: number;
  } | null;
  default_workflow: WorkflowOption | null;
  workflows: WorkflowOption[];
};

const DEFAULT_WORKFLOW = '__project_default__';

export type DispatchResult = {
  request: {
    id: string;
    title: string | null;
    prompt: string;
  };
  workflow: {
    id: string;
  };
  replayed: boolean;
};

type Problem = { detail?: string };

async function readDispatch(response: Response): Promise<DispatchResult> {
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as Problem;
    throw new Error(
      problem.detail ?? `요청을 제출하지 못했습니다. (${response.status})`,
    );
  }
  return (await response.json()) as DispatchResult;
}

export function RequestComposer({
  project,
  onDispatched,
}: {
  project: ProjectSummary | null;
  onDispatched: (result: DispatchResult) => void;
}) {
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workflowOptions, setWorkflowOptions] =
    useState<WorkflowOptions | null>(null);
  const [workflowProjectId, setWorkflowProjectId] = useState<string | null>(
    null,
  );
  const [workflowValue, setWorkflowValue] = useState(DEFAULT_WORKFLOW);
  const [workflowErrorProjectId, setWorkflowErrorProjectId] = useState<
    string | null
  >(null);
  const dispatchAttempt = useRef<DispatchAttempt | null>(null);
  const currentWorkflowOptions =
    workflowProjectId === project?.id ? workflowOptions : null;
  const workflowError = workflowErrorProjectId === project?.id;
  const requiresWorkflowSelection =
    currentWorkflowOptions !== null &&
    currentWorkflowOptions.default === null &&
    workflowValue === DEFAULT_WORKFLOW;
  const selectedWorkflow = currentWorkflowOptions?.workflows.find(
    (workflow) => {
      if (workflowValue !== DEFAULT_WORKFLOW) {
        return `${workflow.key}@${workflow.version}` === workflowValue;
      }
      return false;
    },
  );
  const displayedWorkflow =
    workflowValue === DEFAULT_WORKFLOW
      ? currentWorkflowOptions?.default_workflow
      : selectedWorkflow;

  const clearError = () => {
    setError(null);
  };

  useEffect(() => {
    let active = true;
    if (!project) return () => undefined;
    void fetch(`/api/workflows?projectId=${encodeURIComponent(project.id)}`)
      .then(async (response) => {
        if (!response.ok) throw new Error('workflow options unavailable');
        const options = (await response.json()) as WorkflowOptions;
        if (active) {
          setWorkflowOptions(options);
          setWorkflowProjectId(project.id);
          setWorkflowValue(DEFAULT_WORKFLOW);
          setWorkflowErrorProjectId(null);
        }
      })
      .catch(() => {
        if (active) setWorkflowErrorProjectId(project.id);
      });
    return () => {
      active = false;
    };
  }, [project]);

  const submit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project || !prompt.trim() || submitting) return;

    const input = {
      projectId: project.id,
      title: title.trim() || null,
      prompt: prompt.trim(),
      workflow: selectedWorkflow
        ? {
            definitionKey: selectedWorkflow.key,
            definitionVersion: selectedWorkflow.version,
          }
        : null,
    };
    const attempt = prepareDispatchAttempt(dispatchAttempt.current, input);
    dispatchAttempt.current = attempt;
    setSubmitting(true);
    setError(null);
    try {
      const result = await readDispatch(
        await fetch('/api/dispatch', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': attempt.key,
          },
          body: JSON.stringify(input),
        }),
      );
      dispatchAttempt.current = null;
      setTitle('');
      setPrompt('');
      onDispatched(result);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : '요청을 제출하지 못했습니다.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="border border-cyan-300/12 bg-cyan-300/4 ring-0">
      <CardHeader className="border-b border-white/7 pb-4">
        <CardTitle>새 작업 요청</CardTitle>
        <CardDescription>
          {project
            ? workflowValue === DEFAULT_WORKFLOW
              ? `${project.name}의 기본 워크플로를 시작합니다.`
              : `${project.name}에서 선택한 워크플로를 시작합니다.`
            : '요청을 제출하려면 프로젝트를 선택하세요.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={submit}
          className="grid gap-4 xl:grid-cols-[minmax(170px,0.5fr)_minmax(190px,0.55fr)_minmax(320px,1.45fr)_auto] xl:items-end"
        >
          <div className="space-y-2">
            <Label htmlFor="request-title" className="text-white/75">
              제목 <span className="font-normal text-white/35">선택</span>
            </Label>
            <Input
              id="request-title"
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
                clearError();
              }}
              maxLength={255}
              placeholder="예: 로그인 오류 수정"
              className="h-10 border-white/10 bg-black/15 text-white placeholder:text-white/25"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="request-workflow" className="text-white/75">
              워크플로
            </Label>
            <NativeSelect
              id="request-workflow"
              value={workflowValue}
              onChange={(event) => {
                setWorkflowValue(event.target.value);
                clearError();
              }}
              disabled={!project}
              className="w-full"
              aria-describedby={
                workflowError ? 'workflow-options-error' : undefined
              }
            >
              <NativeSelectOption
                value={DEFAULT_WORKFLOW}
                disabled={
                  currentWorkflowOptions !== null &&
                  currentWorkflowOptions.default === null
                }
              >
                {currentWorkflowOptions?.default
                  ? `프로젝트 기본 · ${currentWorkflowOptions.default.definition_key}@${currentWorkflowOptions.default.definition_version}`
                  : currentWorkflowOptions
                    ? '기본값 없음 · 워크플로 선택'
                    : '프로젝트 기본'}
              </NativeSelectOption>
              {currentWorkflowOptions?.workflows.map((workflow) => (
                <NativeSelectOption
                  key={workflow.id}
                  value={`${workflow.key}@${workflow.version}`}
                >
                  {workflow.key}@{workflow.version}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            {workflowError && (
              <p
                id="workflow-options-error"
                className="text-xs text-amber-100/65"
              >
                선택 목록을 불러오지 못해 프로젝트 기본값을 사용합니다.
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="request-prompt" className="text-white/75">
              요청 내용
            </Label>
            <Textarea
              id="request-prompt"
              required
              value={prompt}
              onChange={(event) => {
                setPrompt(event.target.value);
                clearError();
              }}
              placeholder="완료할 작업, 제약 조건과 기대 결과를 적어주세요."
              className="min-h-20 resize-y border-white/10 bg-black/15 text-white placeholder:text-white/25"
            />
          </div>

          <Button
            type="submit"
            disabled={
              !project ||
              !prompt.trim() ||
              submitting ||
              requiresWorkflowSelection
            }
            className="h-10 gap-2 bg-cyan-300 text-slate-950 hover:bg-cyan-200 xl:mb-0.5"
          >
            {submitting ? (
              <LoaderCircle
                aria-hidden="true"
                className="size-4 animate-spin"
              />
            ) : (
              <ArrowUpRight aria-hidden="true" className="size-4" />
            )}
            {submitting ? '제출 중' : '워크플로 시작'}
          </Button>
        </form>
        {error && (
          <p
            role="alert"
            className="mt-3 rounded-lg border border-red-300/20 bg-red-300/8 px-3 py-2.5 text-sm leading-6 text-red-100"
          >
            {error}
          </p>
        )}
        {displayedWorkflow && (
          <section
            aria-label="선택한 워크플로 구성"
            className="mt-4 rounded-xl border border-white/8 bg-black/15 p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-white/90">
                  {displayedWorkflow.key}@{displayedWorkflow.version}
                </p>
                <p className="mt-1 text-xs text-white/40">
                  시작 노드 {displayedWorkflow.entry_node} · 단계{' '}
                  {displayedWorkflow.nodes.length}개 · 연결{' '}
                  {displayedWorkflow.edges.length}개
                </p>
              </div>
              <div className="flex flex-wrap justify-end gap-1.5 text-xs">
                {displayedWorkflow.phase_packs.map((phasePack) => (
                  <span
                    key={`${phasePack.key}@${phasePack.version}`}
                    title={phasePack.description}
                    className="rounded-full border border-violet-300/15 bg-violet-300/8 px-2 py-1 text-violet-100/70"
                  >
                    {phasePack.name} · Phase
                  </span>
                ))}
                {displayedWorkflow.skills.map((skill) => (
                  <span
                    key={`${skill.key}@${skill.version}`}
                    title={skill.description}
                    className="rounded-full border border-cyan-300/15 bg-cyan-300/8 px-2 py-1 text-cyan-100/70"
                  >
                    {skill.name} · {skill.source_kind}
                  </span>
                ))}
              </div>
            </div>
            <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {displayedWorkflow.nodes.map((node) => (
                <div
                  key={node.key}
                  className="rounded-lg border border-white/7 bg-white/3 px-3 py-2.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-white/80">{node.key}</span>
                    <span className="text-xs uppercase tracking-wide text-white/35">
                      {node.kind}
                    </span>
                  </div>
                  {(node.phase_pack || node.skills.length > 0) && (
                    <p className="mt-1.5 text-xs leading-5 text-white/40">
                      {node.phase_pack &&
                        `Phase ${node.phase_pack.key}@${node.phase_pack.version}`}
                      {node.phase_pack && node.skills.length > 0 ? ' · ' : ''}
                      {node.skills.length > 0 &&
                        `직접 Skill ${node.skills
                          .map((skill) => `${skill.key}@${skill.version}`)
                          .join(', ')}`}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}
        <p className="mt-3 text-xs leading-5 text-white/35">
          요청은 Jarvis가 직접 실행하지 않고 Control Plane에 등록합니다.
        </p>
      </CardContent>
    </Card>
  );
}
