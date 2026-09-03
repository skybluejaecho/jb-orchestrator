# ADR 0020: Workflow 상태를 Run과 Request 생명주기에 원자적으로 반영한다

## 상태

승인됨

## 배경

Workflow Execution은 실제 실행 상태를 알고 있지만 기존 Run 상태는 별도 API에서만
변경됐다. 그 결과 Workflow가 실행 또는 종료되어도 Run이 `queued`에 남고, 성공한 요청도
`active`로 보일 수 있었다. Jarvis와 외부 클라이언트가 어느 aggregate를 조회하느냐에 따라
서로 다른 현재 상태를 표시하게 되는 문제다.

초기 Run 상태에는 `planning`, `ready`, `verifying`처럼 고정된 개발 절차의 의미도 포함돼
있다. Phase Pack을 자유롭게 조립하는 구조에서는 기획 다음에 반드시 개발이나 검증이
실행된다고 가정할 수 없다. 단계의 의미는 Workflow 노드가 소유하고 Run은 전체 실행
상태만 표현해야 한다.

## 결정

- Workflow Execution을 실행 상태의 기준으로 삼고 동일 트랜잭션에서 Run에 투영한다.
- 새 Workflow 기반 Run은 다음 상태 흐름을 사용한다.

```text
queued ─> running <─> awaiting_approval ─> succeeded
   │          │               │
   └──────────┴───────────────┼───────> failed
                              └───────> cancelled
```

- 시작 노드가 승인이라면 `queued`에서 `awaiting_approval`로 직접 이동할 수 있다.
- 즉시 terminal에 도달하는 Workflow도 queued에서 terminal 상태로 직접 이동할 수 있다.
- Workflow 성공 시 Run을 `succeeded`, Request를 `completed`로 변경한다.
- Workflow 실패 시 Run을 `failed`로 변경하되 Request는 `active`로 유지한다. 재시도는 같은
  Request 아래 새로운 Run attempt로 표현한다.
- Workflow 취소 시 Run과 아직 열린 Request를 모두 `cancelled`로 변경한다.
- Run 취소 API에 활성 Workflow가 있으면 Workflow부터 잠그고 전체 계층을 함께 취소한다.
- Workflow가 존재하는 Run의 승인은 모호한 Run 단위 승인 API로 처리하지 않고 정확한
  approval node를 지정해야 한다.
- 각 실제 변경에 `run.status_changed`, `request.completed`, `request.cancelled` 이벤트를
  기록한다.
- 동시 상태 변경은 Workflow Execution, Run, User Request 순서로 row lock을 획득한다.
- 기존 `planning`, `ready`, `verifying` 값은 저장 데이터와 수동 실행 호환성을 위해 당장은
  유지하지만 새 Workflow 실행 경로에서는 생성하지 않는다.
- 요청 문맥이 없는 과거 Workflow 스냅샷은 부모 aggregate를 확정할 수 없으므로 생명주기
  투영을 건너뛴다.

## 결과

사용자 요청, 전체 Run, Workflow와 노드 상태가 하나의 PostgreSQL 트랜잭션 경계에서
일관되게 변경된다. GUI는 각 계층을 조회해도 같은 실행 결과를 표시할 수 있고, Workflow는
기획·개발·검증의 고정 순서를 강제하지 않는다.

후속 작업에서는 dispatch 멱등성, 실패 Run의 명시적 재시도 API, 프로젝트 단위 통합
조회와 SSE projection을 추가한다. 충분한 마이그레이션 기간 이후 사용되지 않는 legacy Run
상태 제거를 별도로 검토한다.
