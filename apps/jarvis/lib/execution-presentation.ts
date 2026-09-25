type ExecutionNode = {
  node_key: string;
  status: string;
};

type ReadableField = {
  label: string;
  values: string[];
};

const fieldLabels: Record<string, string> = {
  acceptance_checks: '완료 기준',
  changed_files: '변경 파일',
  checks: '확인한 항목',
  diagnosis: '진단',
  findings: '발견 사항',
  objective: '목표',
  recommendation: '권고',
  remaining_risks: '남은 위험',
  required_changes: '필요한 수정',
  risks: '위험',
  steps: '진행 단계',
  summary: '요약',
  verdict: '검증 판정',
};

const headlineKeys = [
  'summary',
  'recommendation',
  'diagnosis',
  'objective',
  'message',
  'output',
] as const;

function textValue(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null;
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return null;
}

function fieldValues(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => {
      const text = textValue(item);
      return text ? [text] : [];
    });
  }
  const text = textValue(value);
  return text ? [text] : [];
}

function verdictLabel(value: unknown): string | null {
  if (value === 'approve') return '검증 통과';
  if (value === 'changes_requested') return '수정 필요';
  return null;
}

export function presentStructuredContent(content: Record<string, unknown>): {
  headline: string | null;
  fields: ReadableField[];
} {
  const nested = content.output;
  const source =
    nested !== null && typeof nested === 'object' && !Array.isArray(nested)
      ? (nested as Record<string, unknown>)
      : content;

  const headline =
    headlineKeys.map((key) => textValue(source[key])).find(Boolean) ??
    verdictLabel(source.verdict);
  const fields = Object.entries(source).flatMap(([key, value]) => {
    const values = fieldValues(value);
    if (values.length === 0 || (headline && values[0] === headline)) return [];
    return [{ label: fieldLabels[key] ?? key.replaceAll('_', ' '), values }];
  });

  return { headline, fields };
}

export function summarizeExecutionProgress(
  status: string,
  nodes: ExecutionNode[],
): { message: string; completed: number; total: number } {
  const completed = nodes.filter((node) =>
    ['succeeded', 'failed', 'cancelled'].includes(node.status),
  ).length;
  const active = (nodeStatus: string) =>
    nodes
      .filter((node) => node.status === nodeStatus)
      .map((node) => node.node_key);

  if (status === 'succeeded') {
    return {
      message: '워크플로 실행이 완료되었습니다.',
      completed,
      total: nodes.length,
    };
  }
  if (status === 'failed') {
    return {
      message: '워크플로 실행이 실패했습니다.',
      completed,
      total: nodes.length,
    };
  }
  if (status === 'cancelled') {
    return {
      message: '워크플로 실행이 취소되었습니다.',
      completed,
      total: nodes.length,
    };
  }

  const approvals = active('awaiting_approval');
  if (approvals.length > 0) {
    return {
      message: `${approvals.join(', ')} 단계에서 승인을 기다리고 있습니다.`,
      completed,
      total: nodes.length,
    };
  }
  const running = active('running');
  if (running.length > 0) {
    return {
      message: `${running.join(', ')} 단계를 실행하고 있습니다.`,
      completed,
      total: nodes.length,
    };
  }
  const ready = active('ready');
  if (ready.length > 0) {
    return {
      message: `${ready.join(', ')} 단계의 실행을 기다리고 있습니다.`,
      completed,
      total: nodes.length,
    };
  }
  return {
    message: '다음 단계를 준비하고 있습니다.',
    completed,
    total: nodes.length,
  };
}
