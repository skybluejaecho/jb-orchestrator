# ADR 0036: Artifact 조건 분기는 제한된 결정론적 정책으로 평가한다

## 상태

승인됨

## 배경

Task의 실행 성공 여부만으로는 검증 결과의 의미를 표현하기 어렵다. 출력 계약을 만족하는
`{"verdict": "changes_requested"}`는 정상적으로 생성된 Artifact이므로 executor 실패로 바꾸면
안 된다. 반대로 Agent가 다음 노드까지 직접 선택하게 하면 같은 입력의 경로를 재현하기 어렵고
Workflow 정의가 실제 제어권을 잃는다.

## 결정

- 조건은 Task 간선에만 선택적으로 선언한다. Approval, Fork, Join과 Terminal의 라우팅 의미는
  기존 outcome 규칙을 유지한다.
- 조건은 RFC 6901 JSON Pointer `path`와 JSON scalar `equals`의 엄격한 타입·값 일치만 지원한다.
- 조건은 Phase 출력 계약 검증 후 확정된 Artifact에 적용한다.
- 하나의 source/outcome에 여러 조건 간선을 둘 수 있지만 모두 같은 경로를 사용하고 값은 서로
  달라야 한다. 따라서 두 조건이 동시에 선택되는 정의를 등록 단계에서 차단한다.
- 같은 source/outcome에는 조건 없는 default 간선을 최대 하나 둘 수 있다.
- 조건과 일치하는 간선이 없으면 default를 사용한다. default도 없으면 Workflow를
  `no matching edge` 사유로 실패시킨다.
- 조건과 간선은 Workflow Definition 및 실행 Snapshot에 함께 저장한다. 기존 condition 없는
  직렬화 데이터는 그대로 읽는다.
- 조건 평가는 외부 호출이나 LLM 판단을 사용하지 않는다.

## 흐름

```text
contract-valid Task Artifact
            │
            ▼
JSON Pointer scalar lookup
     ├─ exact match ──> matching edge
     ├─ no match ─────> default edge
     └─ no default ───> deterministic workflow failure
```

## 결과

검증 Agent는 구조화된 판단 근거와 verdict만 반환하고, 실제 다음 단계는 Snapshot에 고정된 정책이
선택한다. 이로써 자동 보정 루프를 구성할 수 있으면서도 세션 기억이나 Agent의 임의 결정에
의존하지 않는다. 범위 비교, 논리 조합, 다중 Artifact 조건과 LLM judge는 별도 정책 버전과
모호성 규칙이 필요하므로 이번 범위에 포함하지 않는다.
