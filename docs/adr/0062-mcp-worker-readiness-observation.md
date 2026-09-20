# ADR 0062: MCP Control Agent는 프로젝트 범위 배정 진단을 읽는다

## 배경

ORCH-064 이후 Worker 배정 경보는 Jarvis와 독립적으로 유지되지만, MCP로 연결된 OpenClaw 같은
Control Agent에는 그 원장을 조회하는 도구가 없었다. 이 차이는 같은 요청을 다루더라도 입력
주체에 따라 상태 설명과 복구 안내가 달라지게 만든다.

## 결정

- MCP 서버에 읽기 전용 `get_worker_readiness(project_id)` 도구를 제공한다.
- 도구는 별도 판단을 복제하지 않고 Control Plane의 프로젝트 범위 GET API를 호출한다.
- 기존 `project.read` 권한과 프로젝트 scope를 그대로 적용한다.
- 응답은 capability coverage, 현재 issue, 영속 경보와 recommended action을 보존한다.
- Control Agent는 진단 결과를 설명할 수 있지만 Worker 시작·재시작이 실행됐다고 추측하지 않는다.
- 전체 Worker 목록은 호스트 정보와 PID를 포함하므로 이 프로젝트 범위 도구에 포함하지 않는다.

## 결과

Jarvis와 MCP Control Agent가 동일한 PostgreSQL 원장을 기준으로 멈춘 READY 작업을 설명할 수
있다. 실제 Worker 제어 및 외부 알림 전달은 별도의 권한과 정책을 요구하는 후속 기능으로 남는다.
