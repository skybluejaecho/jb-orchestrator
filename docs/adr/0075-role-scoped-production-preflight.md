# ADR 0075: 운영 사전 점검은 배포 역할별 실제 설정 계약을 검사한다

## 상태

채택

## 배경

릴리스 품질 게이트가 성공해도 배포 host에 필요한 adapter, credential, filesystem 경계 또는
database migration이 누락될 수 있다. 기존 `jb doctor`는 핵심 설정의 존재 여부를 보여주는 개발용
진단이며, 어떤 process를 실행할지 구분하거나 실패 종료 코드를 제공하지 않는다. 모든 host에 모든
설정을 강제하면 역할 분리 배포가 불가능하고 불필요한 credential까지 복제하게 된다.

## 결정

- `jb system preflight`는 전체 역할 또는 반복된 `--role`로 선택한 역할만 검사한다.
- Control Plane, Task Worker, SCM Worker, Notification Worker와 Readiness Monitor는 PostgreSQL
  연결 및 현재 Alembic revision이 application head와 정확히 일치하는지 확인한다.
- production Control Plane은 bind 주소와 관계없이 인증을 요구한다. production의 원격 MCP,
  Jarvis Control Plane URL은 HTTPS를 요구하며 API token의 존재를 확인한다.
- Task Worker, SCM Worker와 Notification Worker는 각각의 entry-point registry를 실제로
  구성한다. 설치 누락과 adapter factory의 설정 오류는 동일한 역할 실패로 보고한다.
- OpenClaw executor가 설치된 경우 bridge file, Node 실행 파일, Gateway URL, 원격 WSS TLS pin,
  bootstrap credential 또는 저장된 device token을 추가 확인한다.
- 결과는 `pass`, `warning`, `fail` check 목록과 집계를 JSON으로 출력한다. warning은 개발 또는
  staging 점검을 허용하지만 하나의 fail이라도 있으면 명령은 종료 코드 1을 반환한다.
- 예외 형식과 설정 여부만 보고하며 URL 이외의 credential 값과 provider 내부 오류 문자열은
  출력하지 않는다.
- Preflight는 database 이외의 외부 서비스에 연결하지 않는다. 실제 GitHub, Webhook과 OpenClaw
  Gateway 동작은 비용과 외부 변경을 수반할 수 있으므로 별도의 명시적 acceptance로 유지한다.

## 결과

- 한 서버가 담당하는 역할에 필요한 최소 credential만 배치할 수 있다.
- supervisor와 배포 자동화는 구조화된 출력과 종료 코드로 시작 여부를 결정할 수 있다.
- schema가 뒤처진 database나 설정되지 않은 provider로 Worker를 시작하는 실수를 사전에 찾는다.
- CLI option으로만 전달되는 Worker ID, SCM workspace scope와 재시도 정책은 실제 process manifest가
  소유하며 다음 배포 구성 단계에서 검증한다.
