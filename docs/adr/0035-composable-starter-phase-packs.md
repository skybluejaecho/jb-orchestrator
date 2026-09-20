# ADR 0035: Starter Kit은 독립 Phase Pack과 선택 가능한 Workflow 예제를 제공한다

## 상태

부분 대체됨 (ADR 0036)

## 배경

선언형 Bundle만 제공하면 사용자는 모든 Phase Pack, 출력 계약과 Workflow 그래프를 처음부터
작성해야 한다. 하나의 `기획 → 개발 → 검증` 절차를 제품 기본값으로 고정하면 빠르게 시작할 수
있는 대신 jb-orchestrator의 조립 가능성을 다시 제한한다. 또한 OpenClaw의 완료 응답은 provider
terminal envelope 안에 있어, 그 전체를 Artifact로 사용하면 Phase Pack의 출력 계약이 실제
에이전트 JSON을 검사하지 못한다.

## 결정

- `jb bundle init [destination]`은 패키지에 포함된 Starter Kit을 새 디렉터리에 원자적으로
  복사하며 기존 경로를 덮어쓰지 않는다.
- Starter Skill은 일반 `SKILL.md` 디렉터리이고 catalog digest와 실제 파일 digest가 일치한다.
- planning, implementation, verification, repair, review-synthesis Phase Pack을 서로 독립된
  versioned 재료로 제공한다. repair와 synthesis는 여러 Skill 조합을 예시한다.
- planning-only, standard-delivery, parallel-verification Workflow를 함께 제공한다. 사용자는 그중
  하나를 binding하거나 Phase Pack을 다른 그래프로 다시 조립할 수 있다.
- standard-delivery의 repair loop는 executor 실패나 출력 계약 위반을 한 번 보정하는 bounded
  예제다. 검증의 `verdict` 자체는 자동 분기 조건이 아니며 명시적 approval node에서 사람이
  결정한다.
- parallel-verification은 명시적 fork/all-source join으로 두 개의 독립 검증 결과를 모은 뒤
  synthesis Phase에 이름 있는 입력으로 전달한다.
- OpenClaw terminal의 `output`이 JSON object 또는 JSON object 문자열이면 이를 Phase Artifact로
  승격한다. 원본 terminal과 provider 실행 정보는 기존 external execution ledger에 보존한다.
  구조화할 수 없는 출력은 진단 가능한 provider envelope를 유지한다.
- 출력 계약이 있는 OpenClaw 작업에는 Markdown fence 없는 단일 JSON object를 반환하라는
  지시를 추가한다.

## 결과

사용자는 검증된 예제를 즉시 복사하면서도 고정된 lifecycle에 종속되지 않는다. Starter Kit은
자동 적용하지 않으며 Project, OpenClaw agent 설정과 로컬 Skill root를 검토한 뒤 기존
`validate`, `plan`, `apply` 순서로 적용한다. 의미 기반 자동 분기는 별도 정책 기능으로 남긴다.

## 후속 결정

ADR 0036은 마지막 문장의 후속 범위를 구현했다. `standard-delivery`의 contract-valid verdict는
이제 Snapshot에 고정된 조건 정책으로 approval 또는 repair에 분기된다. Phase Pack과 Workflow가
선택 가능한 조립 재료라는 나머지 결정은 유지된다.
