# ADR 0037: 요청별 Workflow 선택은 프로젝트 기본값 위의 명시적 override다

## 상태

승인됨

## 배경

프로젝트마다 하나의 Workflow binding만 사용하면 기본 운영 흐름은 단순하지만, 같은 프로젝트에서
기획만 수행하거나 병렬 검증을 선택하려면 매번 프로젝트 설정을 바꿔야 한다. Jarvis, OpenClaw와
다른 입력 어댑터가 Workflow를 자유롭게 선택할 수 있어야 하지만, 이름만 지정해 실행 시점의 최신
버전을 따르게 하면 재현성과 멱등 재시도가 흔들린다.

## 결정

- 프로젝트 binding은 선택이 없는 모든 요청의 기본 Workflow로 유지한다.
- dispatch command는 선택적인 `definition_key`와 `definition_version`을 받으며 두 값은 함께
  제공해야 한다.
- 명시적 선택은 해당 요청에만 적용하고 프로젝트 binding을 변경하지 않는다.
- 명시적 선택이 있으면 binding이 없는 프로젝트도 실행할 수 있다.
- 선택한 정확한 정의가 없으면 요청 상태를 만들기 전에 실패한다.
- 선택값을 prompt, title, origin과 함께 dispatch payload digest에 포함한다. 같은 멱등성 key로
  Workflow 선택을 바꾸면 `409 Conflict`로 거부한다.
- `request.created` 이벤트에는 실제 key/version과 `project_binding` 또는 `request_override`
  source를 저장한다. 실행 Snapshot에도 기존처럼 정확한 정의 전체를 고정한다.
- 프로젝트 범위 option API는 현재 기본 binding과 선택 가능한 최신 Workflow 버전을 반환한다.
- REST, MCP와 Jarvis는 같은 application service와 option API를 사용한다.
- 자동 분류 모델이나 LLM은 이번 선택 경로에 관여하지 않는다.

## 사용자 흐름

```text
Jarvis / OpenClaw / 다른 Client
              │
              ├─ option 조회 ──> default + exact workflow versions
              │
              └─ dispatch
                   ├─ 선택 없음 ──> project binding
                   └─ key@version ─> request override
                                      │
                                      ▼
                       Request + Run + Snapshot + Events
                                one transaction
```

## 결과

입력 채널은 프로젝트 설정을 변경하지 않고 목적에 맞는 조립형 Workflow를 고를 수 있다. 동시에
선택 버전과 근거가 PostgreSQL 이벤트와 Snapshot에 남아 재시도와 사후 설명이 가능하다. 요청
문장으로 Workflow를 자동 추천하거나 선택하는 정책은 후보 제한, 신뢰도와 사용자 확인 규칙을
먼저 정의한 뒤 별도 기능으로 확장한다.
