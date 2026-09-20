# ADR 0028: Jarvis를 로컬 관찰 UI로 시작한다

## 상태

승인됨

## 배경

사용자는 현재 어떤 프로젝트와 Workflow가 실행 중인지 로컬 GUI에서 확인해야 한다.
Jarvis가 별도의 상태를 소유하거나 OpenClaw를 직접 제어하면 PostgreSQL 원장과 화면이
불일치할 수 있다. 브라우저에 서비스 계정 token을 저장하는 것도 허용할 수 없다.

## 결정

- Jarvis 첫 버전은 `apps/jarvis`의 로컬 전용 관찰 대시보드로 구현한다.
- 프로젝트, 요청, Workflow의 현재 상태는 Control Plane 목록 API에서 읽는다.
- 이후 변경은 프로젝트 SSE stream으로 감지하고 현재 snapshot을 다시 조회한다.
- 브라우저는 같은 origin의 Vinext server route만 호출한다.
- server route가 `JARVIS_API_TOKEN`을 보관하고 Control Plane bearer 인증을 수행한다.
- 첫 버전은 실행, 승인, 취소 같은 쓰기 기능을 제공하지 않는다.
- 프로젝트 목록 조회를 위해 Jarvis 계정은 `project.read`와 `all_projects` 범위를 사용한다.
- 사용자 인증이 추가되기 전까지 외부 배포나 네트워크 공개를 지원하지 않는다.

## 결과

Jarvis는 상태 저장소가 아닌 교체 가능한 GUI adapter로 남는다. OpenClaw, Codex 또는 다른
주체가 작업을 시작해도 동일한 DB 상태를 표시한다. 후속 버전에서 요청 제출과 승인 UI를
추가할 때는 별도 permission과 사용자 확인 절차를 적용한다.
