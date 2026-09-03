# ADR 0017: Phase 출력 계약 위반은 repair 가능한 비즈니스 실패로 처리한다

## 상태

승인됨

## 배경

Phase Pack이 출력 계약을 프롬프트에 전달하더라도 Executor나 모델이 계약과 다른 JSON을
반환할 수 있다. 이 결과를 그대로 성공 Artifact로 저장하면 후속 단계가 누락된 필드를
추측해야 하고, 실행 재현성과 자동 루프의 판정 기준이 무너진다.

계약 위반을 기술 예외로 처리하면 Worker 재시도가 같은 입력과 같은 지시로 반복될 가능성이
높다. 반면 Workflow의 `failure` 분기로 전달하면 검증 실패 정보를 별도의 repair 단계가
입력으로 받아 수정할 수 있다.

## 결정

- `output_contract`는 JSON Schema Draft 2020-12 문서로 해석한다.
- Phase Pack 등록 시 JSON Schema 자체의 유효성을 검증한다.
- 네트워크 의존성과 SSRF를 막기 위해 로컬 fragment가 아닌 외부 `$ref`와 `$dynamicRef`는
  등록 단계에서 거부한다.
- Executor가 `success`를 반환한 경우에만 Phase 출력 계약을 검사한다.
- 유효한 출력은 변경하지 않는다.
- Executor가 명시적으로 반환한 `failure` 출력은 계약 검증으로 덮어쓰지 않는다.
- 성공 출력이 계약을 위반하면 결과를 `failure`로 변환한다.
- 변환된 Artifact에는 Phase Pack 버전, JSON 경로, 검증 키워드, 오류 메시지와 원본 출력을
  구조적으로 보존한다.
- Workflow Engine은 변환된 `failure` 결과를 기존 실패 간선으로 라우팅한다.
- 별도의 실패 간선이 없으면 기존 Workflow 규칙에 따라 실행이 실패한다.
- 모델 사용 비용은 실제로 소비되었으므로 출력 계약 위반 여부와 관계없이 정산한다.

## 흐름

```text
Executor result: success
          │
          ▼
JSON Schema validation
    ├─ valid ───────> success Artifact ──> success edge
    │
    └─ invalid ─────> failure Artifact ──> failure edge ──> repair node
                         │
                         ├─ structured validation errors
                         └─ rejected original output
```

## 결과

출력 계약은 문서가 아니라 실행 가능한 판정 기준이 된다. 검증 실패는 PostgreSQL Artifact와
Event에 남고, repair 노드는 일반 선행 Artifact처럼 오류와 원본 출력을 전달받는다. 따라서
검증과 수정 루프를 특정 Executor 세션이나 대화 기억에 의존하지 않고 재현할 수 있다.

현재 검증은 JSON Artifact 전체에 적용한다. 대용량 외부 Artifact의 내용 검증과 사용자 정의
검증 플러그인은 별도 확장으로 남긴다.
