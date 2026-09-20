# ADR 0050: SCM 게시는 실제 어댑터를 사용하는 process smoke로 검증한다

## 상태

승인됨

## 배경

SCM 게시 원장, lease 기반 Worker와 GitHub Publisher는 각각 테스트되지만 실제 설치 환경에서
entry point 발견, PostgreSQL claim, Git push와 HTTP 결과 저장이 한 번에 연결된다는 보장은
없다. 실제 GitHub 저장소를 CI에서 변경하면 credential, 네트워크와 정리 정책 때문에 필수 품질
게이트가 불안정해진다.

## 결정

- 기존 `jb system smoke`에 SCM 게시 요청과 별도 `jb-scm-worker` process를 포함한다.
- smoke는 임시 feature worktree와 bare Git remote를 만든다. worktree의 remote identity는
  GitHub 형식을 유지하고 Git의 repository-local `url.*.insteadOf` 설정으로 push만 임시 bare
  remote에 전달한다.
- loopback HTTP server는 GitHub pull-request 조회·생성 계약의 최소 응답만 제공한다.
- GitHub Publisher의 HTTP 예외는 명시적 설정, loopback host, `JB_ENVIRONMENT=test`를 모두
  만족할 때만 허용한다. 기본값과 운영 환경에서는 HTTPS를 강제한다.
- smoke는 실제 GitHub Publisher entry point를 로드하고 게시 결과가 PostgreSQL 원장에
  `succeeded`로 저장되었는지 Control Plane API로 다시 읽는다.
- 외부 GitHub 호출, 실제 PR 생성, merge와 원격 branch 정리는 수행하지 않는다.

## 결과

필수 CI가 외부 credential 없이도 Control Plane → PostgreSQL → SCM Worker → GitHub Adapter →
Git push/PR API → PostgreSQL 결과의 process 경계를 검증한다. test 전용 우회가 운영 설정에서
활성화되면 adapter factory가 시작을 거부한다.
