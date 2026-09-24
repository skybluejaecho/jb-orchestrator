# PostgreSQL 백업·복원 리허설

`postgres-data`는 오케스트레이션의 원장이다. OpenClaw device 상태, Skill cache, repository와
worktree는 별도 저장 경계이므로 이 DB dump만으로 전체 host가 복원되지는 않는다. 실제 운영
복구 계획에는 각 경계의 백업·보존 기간과 복원 순서를 별도로 기록한다.

## 백업 전 점검

1. 정확한 서버 Compose project와 database volume을 확인한다. 운영 중인 다른 프로젝트의
   PostgreSQL을 대상으로 명령을 실행하지 않는다.
2. Credential token이 아닌 database dump 자체도 민감한 운영 정보로 취급한다. 암호화된 위치에
   저장하고 접근 권한·보존 기간을 정한다.
3. 일관된 복구 시점을 만들려면 새 요청과 Worker 처리를 멈추고, 각 프로세스가 가진 진행 중
   작업의 원장 상태를 확인한다. 백업 파일을 만드는 동안 volume을 삭제하거나 재생성하지 않는다.
4. 아래 리허설은 **새로 만든 일회용 database**에만 복원한다. 기존 운영 database에
   `pg_restore --clean`을 직접 실행하지 않는다.

## 백업

서버 host에서 `deploy/server/.env`가 준비된 경우:

~~~powershell
docker compose --env-file deploy/server/.env -f deploy/server/compose.yml ps postgres
docker compose --env-file deploy/server/.env -f deploy/server/compose.yml `
  exec -T postgres pg_dump -U jb_orchestrator -d jb_orchestrator -Fc `
  -f /tmp/jb-orchestrator.dump
docker compose --env-file deploy/server/.env -f deploy/server/compose.yml `
  cp postgres:/tmp/jb-orchestrator.dump ./jb-orchestrator-0.1.0.dump
~~~

`pg_dump` 완료 상태와 dump 파일 크기를 확인한 뒤 안전한 백업 저장소로 옮긴다. 컨테이너의
`/tmp/jb-orchestrator.dump`는 백업 검증 후 제거한다. 비밀번호나 dump 본문을 터미널 로그에
출력하지 않는다.

## 복원 리허설

운영 volume이 아닌 새 PostgreSQL 인스턴스와 새 database를 준비한 후 dump를 복사하고:

~~~powershell
docker cp ./jb-orchestrator-0.1.0.dump <disposable-postgres-container>:/tmp/jb-orchestrator.dump
docker exec <disposable-postgres-container> `
  pg_restore -U jb_orchestrator -d jb_orchestrator --no-owner --exit-on-error `
  /tmp/jb-orchestrator.dump
docker exec <disposable-postgres-container> `
  psql -U jb_orchestrator -d jb_orchestrator -Atc "SELECT version_num FROM alembic_version"
~~~

Alembic revision이 해당 release head와 일치하는지 확인하고, 복원된 프로젝트·요청·실행·감사
기록을 읽기 전용으로 표본 검사한다. 원본과 복원본의 row 수·최신 event sequence를 비교하고,
검증 실패 시 실제 서버를 가동하지 않는다. 복원 테스트가 끝나면 일회용 인스턴스만 정리한다.

## 이미지 rollback

서버와 Jarvis의 `.env`에 기록된 이미지 tag를 이전 안정 버전으로 되돌린 뒤 각 Compose에서
`pull`과 `up -d`를 실행한다. Schema migration이 이전 이미지와 호환되는지 먼저 확인한다.
호환되지 않으면 이미지 rollback만 시도하지 말고 검증된 database backup의 별도 복원 계획을
사용한다. 일반 재시작이나 rollback에 `docker compose down --volumes`를 사용하지 않는다.
