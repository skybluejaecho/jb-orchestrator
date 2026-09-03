# ADR 0022: 프로젝트 관찰은 관계 기반 조회와 단일 SSE로 제공한다

## 상태

승인됨

## 배경

Jarvis 같은 로컬 GUI가 전체 작업 현황을 표시하려면 Project, User Request, Run,
Workflow Execution을 각각 알고 조합해야 했다. 외부 실행 SSE만으로는 승인 대기나
Workflow 종료 같은 내부 상태 변화를 한 연결에서 관찰할 수도 없었다.

이벤트마다 `project_id`를 다시 저장하면 조회는 단순해지지만 동일한 소속 정보를 여러
곳에서 관리하게 된다. 기존 데이터의 backfill과 모든 이벤트 생산자의 누락 방지도
필요하다.

## 결정

- Project, User Request, Run, Workflow Execution에 필터와 limit를 지원하는 목록 조회를
  추가한다.
- 목록은 최신 상태부터 반환하고 이벤트는 원장의 sequence 오름차순으로 반환한다.
- 프로젝트 이벤트 범위는 PostgreSQL의 기존 관계를 따라 계산한다.
  - Project 직접 이벤트
  - Project의 Request와 그 Run
  - Run에 연결된 Workflow Execution 및 External Execution
  - Project의 Budget Account 및 Budget Reservation
- Skill, Phase Pack, Model, Workflow Definition 같은 전역 카탈로그 이벤트는 제외한다.
- `GET /v1/projects/{project_id}/events/stream`은 저장 이벤트를 먼저 재생한 뒤 polling으로
  tail한다.
- SSE `id`에는 event UUID를 사용하고 `Last-Event-ID` 또는 `after` cursor 이후부터
  재개한다. 두 cursor가 다르면 요청을 거부한다.
- SSE data에는 공통 `aggregate_type`과 `aggregate_id`를 포함한다. 기존 External
  Execution 스트림의 `external_execution_id` 필드는 호환성을 위해 유지한다.

## 결과

GUI와 다른 클라이언트는 API가 제공하는 프로젝트 경계를 그대로 사용하며 자체 조인이나
세션 메모리를 진실의 원천으로 삼지 않는다. 일시적인 연결 해제 뒤에도 PostgreSQL 원장을
기준으로 이벤트를 다시 받을 수 있다.

현재 관계 기반 조회는 이벤트 목록마다 여러 하위 쿼리를 사용한다. 실제 운영 데이터에서
성능을 측정한 뒤 필요하면 별도의 project event projection을 추가하되, 원본 이벤트와의
정합성 및 backfill 절차를 함께 설계한다.
