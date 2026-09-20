# ADR 0018: 명시적 fork/join으로 병렬 단계를 조정한다

## 상태

승인됨

## 배경

여러 Task 노드를 단순히 READY 상태로 만들면 외부 에이전트는 동시에 실행할 수 있지만,
언제 모든 결과가 준비되었는지 판단할 수 없다. 또한 서로 다른 Worker가 같은 Workflow의
병렬 노드를 동시에 claim하거나 완료하면 각 트랜잭션이 읽은 aggregate 상태가 달라져 한쪽
전이가 유실될 수 있다.

병렬 실행의 구조와 합류 조건은 에이전트 세션이 아니라 재현 가능한 Workflow 정의와
PostgreSQL 상태로 관리해야 한다.

## 결정

- 실행하지 않는 구조 노드로 `fork`와 `join`을 추가한다.
- `fork`는 `success` 간선을 둘 이상 가져야 하며 모든 대상 노드를 활성화한다.
- `join`은 직접 선행 소스를 둘 이상 가져야 한다.
- `join`은 모든 직접 선행 노드가 완료 상태가 될 때까지 PENDING으로 유지한다.
- 마지막 선행 노드가 완료되면 `join`을 성공 처리하고 다음 노드를 활성화한다.
- Task, approval 및 일반 분기는 기존처럼 한 outcome당 하나의 대상만 허용한다.
- 초기 구현의 제어 의미를 명확하게 유지하기 위해 fork/join은 한 번만 방문할 수 있고
  graph loop에 포함될 수 없다. Task 기반 repair loop는 계속 지원한다.
- 병렬 분기가 terminal에 도달하거나 Workflow가 실패하면 남아 있는 READY, RUNNING,
  AWAITING_APPROVAL 형제 노드를 취소한다.

## 동시성 제어

- READY 선택 시 Node row가 아니라 해당 Workflow Execution row를 `FOR UPDATE SKIP LOCKED`로
  잠근다.
- claim 트랜잭션은 aggregate 상태를 변경하고 즉시 잠금을 해제한다.
- 실제 Executor 호출은 트랜잭션 밖에서 수행되므로 여러 Worker의 실행 시간은 겹칠 수 있다.
- heartbeat, complete, fail 및 API 기반 상태 전이는 Workflow Execution row를 먼저 잠근다.
- 동일 Workflow의 상태 전이는 짧게 직렬화되어 병렬 완료 결과가 유실되지 않는다.
- 서로 다른 Workflow Execution은 서로 다른 row를 잠그므로 독립적으로 진행된다.

## 흐름

```text
                         ┌─> research task ─┐
request ─> fork(success) ┤                  ├─> join(all) ─> synthesis ─> done
                         └─> design task ───┘

Worker A: claim research ───────── execute ───── complete ┐
                                                          ├─ serialized state updates
Worker B: claim design   ───── execute ───────── complete ┘
```

`synthesis` Phase Pack은 Input Mapping으로 `research`와 `design`의 Artifact를 각각 이름 있는
입력에 연결한다. join 자체는 Artifact를 만들지 않으며 합류 상태만 관리한다.

## 결과

여러 사람 또는 여러 에이전트가 같은 Workflow의 독립 단계를 동시에 처리할 수 있고, 모든
필요 결과가 준비된 뒤에만 후속 단계가 실행된다. 실행 세션은 독립적이어도 합류 판단과
Artifact 전달은 PostgreSQL 상태에서 재현된다.

중첩 병렬 영역, 선택적 any/quorum join, 동적 fan-out, fork/join을 포함하는 반복은 후속
확장으로 남긴다.
