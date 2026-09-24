export type WorkflowCompatibilityIssue = {
  code: string;
  node_key: string;
  executor_key: string;
  message: string;
};

export type WorkflowCompatibility = {
  compatible: boolean;
  compatibility_issues: WorkflowCompatibilityIssue[];
};

export function isWorkflowDispatchBlocked(
  workflow: WorkflowCompatibility | null | undefined,
): boolean {
  return workflow?.compatible === false;
}

export function workflowCompatibilityGuidance(
  issue: WorkflowCompatibilityIssue,
): string {
  switch (issue.code) {
    case 'openclaw.workspace_mode_unsupported':
      return '동적 Git worktree는 현재 OpenClaw 연결에서 지원되지 않습니다. 프로젝트 작업공간이 지정된 OpenClaw 에이전트를 선택하도록 워크플로를 수정해 주세요.';
    case 'openclaw.dynamic_cwd_unsupported':
      return '노드별 cwd 변경은 현재 OpenClaw 연결에서 지원되지 않습니다. 작업 디렉터리는 OpenClaw 에이전트 설정에 지정해 주세요.';
    default:
      return issue.message;
  }
}
