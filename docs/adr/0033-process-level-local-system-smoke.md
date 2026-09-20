# ADR 0033: 전체 로컬 경계를 별도 process smoke test로 검증한다

## 상태

승인됨

## 배경

Python 단위·통합 테스트와 Jarvis 계약 테스트는 각각 빠르고 결정론적이지만 실제 process
배치가 함께 작동한다는 사실을 보장하지 않는다. 환경 변수 이름, 인증 token 전달, executor
entry point 설치, Jarvis server proxy 또는 프로세스 시작 명령이 어긋나도 기존 품질 게이트는
모두 통과할 수 있다.

실제 OpenClaw 같은 외부 runtime을 CI 필수 조건으로 만들면 credential과 네트워크 상태 때문에
검증이 불안정해진다. 반대로 테스트용 executor를 일반 배포에 포함하면 실수로 가짜 결과를
생성할 위험이 있다.

## 결정

- `jb system smoke`가 PostgreSQL을 제외한 Control Plane과 Jarvis를 별도 child process로
  시작하고 실제 Worker process를 한 번 실행한다.
- 호출자는 미리 migration이 적용된 일회용 PostgreSQL database를 제공해야 하며
  `JB_ENVIRONMENT=test`가 아니면 명령을 거부한다.
- smoke 전용 executor는 `tools/system-smoke-executor`의 독립 package로 두고 명령 실행 동안만
  editable dependency로 설치한다. factory도 test 환경이 아니면 fail closed 한다.
- setup service account와 Jarvis service account를 실제 DB에 발급하고 API 인증을 활성화한다.
- Jarvis API를 통해 요청 제출, 실행 상세와 Artifact 조회, 승인, 성공 수렴 및 별도 실행 취소를
  검증한다.
- readiness와 상태 전이에는 제한 시간을 두고 성공과 실패 모두에서 child process tree와 임시
  log를 정리한다. 실패 메시지에는 secret이 아닌 각 process의 마지막 log만 포함한다.
- GitHub Actions에 PostgreSQL service와 Python·Node runtime을 갖춘 독립 system-smoke job을
  둔다.

## 결과

독립 품질 게이트가 놓치던 실제 설치·process·HTTP·인증 경계를 PR마다 검증한다. 외부 agent
provider 자체는 이 smoke의 범위가 아니며 OpenClaw live 검증 절차가 별도로 담당한다. 명령은
smoke record를 자동 삭제하지 않으므로 반드시 폐기 가능한 test database에만 실행해야 한다.
