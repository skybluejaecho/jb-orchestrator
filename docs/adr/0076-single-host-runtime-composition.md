# ADR 0076: 첫 운영 배포는 프로필 기반 단일 호스트 구성으로 제공한다

## 상태

채택

## 배경

각 process의 CLI와 운영 preflight는 존재하지만 사용자가 PostgreSQL, migration, Control Plane,
여러 Worker와 Jarvis를 직접 조합해야 했다. 곧바로 Kubernetes나 서비스별 배포 저장소를 도입하면
아직 측정되지 않은 확장 요구에 비해 운영 복잡도가 커진다. 반대로 모든 역할을 한 컨테이너에
합치면 독립적인 credential과 장애 경계, Worker capability 선택을 잃는다.

## 결정

- 첫 운영 참조는 Docker Compose 기반의 단일 trusted host로 제한한다. 이 결정은 core의 modular
  monolith 구조를 변경하지 않고 process 배치만 표준화한다.
- 하나의 Python runtime image에 core, OpenClaw executor, GitHub publisher, Webhook notifier와
  Node bridge를 설치한다. 각 service는 같은 image에서 자신의 기존 CLI entry point만 실행한다.
- PostgreSQL, migration, API와 Readiness Monitor는 기본 core다. Task Worker, SCM Worker,
  Notification Worker, Jarvis, admin은 각각 명시적 profile로 활성화한다.
- database를 사용하는 process는 one-shot migration의 성공을 시작 조건으로 삼는다. API는 별도
  healthcheck를 제공하고 장기 실행 process에는 restart policy와 graceful stop 시간을 둔다.
- OpenClaw, GitHub, Webhook과 Jarvis credential은 소유 service에만 주입한다. 공통 environment
  anchor에는 비밀값을 두지 않는다.
- Task Worker와 SCM Worker는 동일한 container 경로에 repository와 worktree bind mount를
  공유한다. 따라서 기존 workspace scope hash와 DB에 기록된 할당이 process 간에 일치한다.
- PostgreSQL data와 OpenClaw device identity는 서로 다른 durable volume에 저장한다. Skill cache는
  별도의 재생성 가능 volume으로 분리하고 source repository와 worktree는 host bind mount로 남긴다.
- Jarvis는 build 결과를 `vinext start`로 제공한다. Production Control Plane URL의 DNS, TLS 종료와
  방화벽은 해당 host의 reverse proxy 운영자가 소유하며 Compose가 인증서를 임의 생성하지 않는다.
- CI는 `.env.example`로 모든 profile의 Compose 보간과 schema를 검사한다. 실제 image build와
  process startup은 로컬 acceptance에서 확인한다.

## 결과

- 사용자는 한 서버에서 core만 시작한 뒤 필요한 외부 capability를 profile 단위로 추가할 수 있다.
- 특정 Provider credential을 전체 시스템에 공유하지 않고 Worker를 독립 재시작할 수 있다.
- DB migration과 process 시작 순서가 명시적으로 재현된다.
- 수평 확장, 외부 managed PostgreSQL, image registry, TLS reverse proxy와 Kubernetes 배포는 실제
  운영 부하와 환경 요구가 확인된 뒤 별도 결정으로 확장한다.
