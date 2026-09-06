# ADR 0057: Worker 프로세스 수명과 heartbeat를 작업 lease와 분리해 기록한다

## 배경

기존 heartbeat는 실행 중인 Workflow 노드의 lease를 연장한다. 따라서 작업이 없는 Worker가
실제로 실행 중인지, 어떤 executor·SCM provider·workspace scope를 처리할 수 있는지 Control
Plane과 Jarvis에서 알 수 없다. 프로세스 재시작이 동일한 `worker_id`를 재사용하면 과거 실행과
현재 실행도 구분하기 어렵다.

## 결정

- Worker가 시작할 때마다 UUID를 가진 새 `worker_instances` 레코드를 만든다.
- 사람이 지정한 Worker ID, 종류, hostname, PID, capability와 선택적 workspace scope를 함께
  저장한다.
- 실행 Worker, OpenClaw Workspace Worker, SCM Worker는 같은 presence runtime을 사용한다.
- presence runtime은 작업 유무와 관계없이 주기적으로 `last_seen_at`을 갱신하고 정상 종료 시
  `stopped`를 기록한다.
- 비정상 종료는 별도 정리 작업 없이 마지막 heartbeat와 설정된 임계값을 비교해 `stale`로
  판정한다. 원본 lifecycle 상태는 임의로 덮어쓰지 않는다.
- 작업 lease heartbeat는 실행 소유권을, process heartbeat는 Worker 가용성을 나타내므로 서로
  대체하지 않는다.
- `GET /v1/workers`는 최신 인스턴스부터 online/stale/stopped 파생 상태를 반환한다.
- Jarvis는 30초 polling으로 Worker 현황을 갱신한다. Worker presence는 프로젝트 이벤트가
  아니므로 프로젝트 SSE 원장에 섞지 않는다.

## 결과

PostgreSQL에서 Worker 프로세스의 존재와 작업 실행 상태를 독립적으로 설명할 수 있다. 다음
단계에서는 READY 작업의 executor·scope 요구사항과 online Worker capability를 비교하여 미할당
원인을 진단할 수 있다. 이번 결정은 원격 프로세스 시작·종료 권한을 추가하지 않는다.
