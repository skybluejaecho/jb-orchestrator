# ADR 0016: 실행 단계를 버전 고정 Phase Pack으로 조립한다

## 상태

승인됨

## 배경

Workflow 노드에 역할, 지시문, Skill, 입출력 기대사항을 모두 직접 작성하면 기획, 개발,
검증 단계를 다른 Workflow에서 재사용하기 어렵다. 반대로 `기획 → 개발 → 검증` 순서를
코드에 고정하면 요청에 따라 검증만 실행하거나 기획과 조사를 병렬로 배치하는 구성이
불가능해진다.

ORCH-018은 직접 선행 노드의 최신 Artifact를 자동 전달하지만, Artifact가 어떤 의미의
입력인지 Executor가 추측해야 한다.

## 결정

- Phase Pack은 역할, 공통 지시문, 필요한 Skill, 이름 있는 입력 계약, JSON 출력 계약을
  묶은 불변 버전 단위다.
- Workflow 노드는 정확한 Phase Pack의 `key@version`을 참조한다.
- Workflow 노드의 Input Mapping은 Phase Pack의 입력 이름을 Artifact 생성 노드에 연결한다.
- Workflow 시작 시 참조된 Phase Pack과 Skill의 정확한 버전을 Snapshot에 복사한다.
- 필수 입력 누락과 선언되지 않은 입력 매핑은 Workflow 등록 단계에서 거부한다.
- Worker는 각 매핑을 해당 생성 노드의 최신 Artifact로 해석해 이름 있는 입력으로 전달한다.
- Phase Pack을 사용하지 않는 기존 노드는 직접 선행 Artifact를 받는 기존 동작을 유지한다.
- Node의 실행기, 재시도, 제한 시간, 분기와 모델 라우팅은 Workflow가 계속 소유한다.

## 흐름

```text
Phase Pack catalog
  └─ implementation@1
       ├─ instructions
       ├─ skills[]
       ├─ input: approved_plan
       └─ output contract

Workflow definition
  plan ──> implement ──> verify
             │
             ├─ phase_pack: implementation@1
             └─ approved_plan <- plan

Workflow snapshot
  └─ implementation@1 전체 계약 + 정확한 Skill 버전 고정

Task claim
  └─ named_inputs.approved_plan = latest artifact from plan
```

## 결과

Phase Pack은 재사용 가능한 실행 재료이고 Workflow는 재료를 순서, 분기, 루프 또는 병렬
그래프로 조립한다. 따라서 기획 다음에 반드시 개발이 실행되는 구조가 아니며, 같은 Phase
Pack을 여러 Workflow에서 선택적으로 사용할 수 있다.

현재 입력 매핑은 Artifact 전체 JSON 문서를 전달한다. JSONPath 일부 선택과 여러 Artifact
집계는 별도 확장으로 남긴다. 출력 JSON Schema 강제 검증은 ADR 0017에서 정의한다.
