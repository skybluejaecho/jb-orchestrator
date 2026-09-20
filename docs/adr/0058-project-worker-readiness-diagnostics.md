# ADR 0058: READY 작업과 최신 Worker capability를 비교해 미할당 원인을 설명한다

## 배경

ORCH-060은 Worker process 생존 상태와 capability를 원장에 기록한다. 그러나 Workflow 노드가
READY에 머물러도 사용자는 단순 대기인지, executor를 지원하는 Worker가 없는지, 알려진 Worker가
중단됐는지 알 수 없다. 브라우저에서 두 목록을 임의로 결합하면 stale 임계값과 프로세스 중복
처리가 클라이언트마다 달라진다.

## 결정

- Control Plane이 프로젝트의 RUNNING Workflow에서 READY 노드를 조회한다.
- 각 노드의 `executor_key`를 최신 실행 Worker 인스턴스의 capability와 비교한다.
- 같은 `worker_id`로 여러 프로세스 수명이 있으면 `last_seen_at`이 가장 최신인 인스턴스만 현재
  Worker로 간주한다.
- capability coverage는 online, stale, stopped Worker ID를 구분한다.
- online Worker가 없을 때 알려진 capability 자체가 없으면 `no_capable_worker`, 과거 또는 stale
  Worker만 있으면 `capable_workers_offline`으로 진단한다.
- `GET /v1/projects/{project_id}/worker-readiness`는 `project.read` 범위로 조회하며 진단 시각,
  online 실행 Worker 수, executor별 coverage와 미할당 노드를 반환한다.
- Jarvis는 프로젝트 SSE 변경과 30초 polling 모두에 반응해 진단을 갱신한다.
- 진단은 관찰 기능이며 노드를 직접 재배정하거나 Worker 프로세스를 시작하지 않는다.

## 결과

사용자는 READY 작업이 멈춘 이유를 DB 상태만으로 설명받는다. Worker가 capability와 heartbeat를
등록하면 별도 중앙 scheduler 없이 기존 pull 기반 claim 구조를 유지할 수 있다. 후속 단계에서는
이 보고서를 활용해 배포 설정 오류 알림과 안전한 Worker 시작 안내를 추가할 수 있다.
