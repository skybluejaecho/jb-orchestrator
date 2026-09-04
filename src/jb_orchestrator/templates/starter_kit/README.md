# JB Orchestrator Starter Kit

이 디렉터리는 `jb bundle init`으로 생성된다. `orchestrator.yaml`에는 서로 독립적인 Phase Pack과
세 가지 Workflow 조합이 들어 있다.

- `planning-only`: 구현 없이 기획 결과만 생성
- `standard-delivery`: 기획, 구현, 검증, 명시적 승인과 bounded repair loop
- `parallel-verification`: 하나의 구현 결과를 두 검증 노드가 병렬로 검토한 뒤 종합

로컬 Skill 경로는 이 디렉터리의 `skills`를 기준으로 한다.

```powershell
$env:JB_SKILL_LOCAL_ROOT = (Resolve-Path skills)
uv run jb bundle validate orchestrator.yaml
uv run jb bundle plan orchestrator.yaml
uv run jb bundle apply orchestrator.yaml
```

실제 적용 전 `orchestrator.yaml`의 Project 값과 각 task node의 OpenClaw `configuration`을 환경에
맞게 수정한다. Bundle에 secret이나 Gateway credential을 넣지 않는다.
