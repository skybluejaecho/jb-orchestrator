# ADR 0051: Jarvis의 SCM 게시 제어는 원장 기반 요청으로 제한한다

## 상태

승인됨

## 배경

GitHub Publisher와 SCM Worker가 준비되었지만 사용자는 Control Plane API를 직접 호출해야만
게시를 요청하고 결과를 확인할 수 있다. Jarvis가 GitHub credential이나 Git 경로를 직접 다루면
로컬 관찰 UI와 실행 Adapter의 권한 경계가 무너진다.

## 결정

- Jarvis는 managed external execution 카드 안에 GitHub 게시 패널을 표시한다.
- 외부 실행이 terminal이고 worktree가 아직 release되지 않았을 때만 새 게시 양식을 연다.
- source branch는 원장에서 읽은 값을 고정 표시하고 target branch, PR 제목과 본문은 사용자가
  명시적으로 확인한다.
- 브라우저는 같은 origin의 `/api/scm-publications`만 호출한다. Server route가 입력을 검증하고
  `scm.publish` 권한을 가진 Jarvis service-account token으로 Control Plane을 호출한다.
- 각 요청은 새로운 idempotency key를 가지며 UI는 pending, claimed, succeeded, failed 상태를
  원장에서 다시 읽는다.
- 결과의 review URL은 유효한 HTTPS URL일 때만 새 창 링크로 렌더링한다.
- 프로젝트 SSE의 SCM publication 이벤트는 실행 상세와 게시 이력을 다시 조회하게 한다.
- Jarvis는 GitHub token을 보관하거나 Git push, PR 생성, merge를 직접 수행하지 않는다.

## 결과

사용자는 로컬 GUI에서 게시를 시작하고 진행 상태와 결과 링크를 확인할 수 있다. 실제 원격 변경은
workspace scope에 배치된 SCM Worker와 Adapter만 수행하므로 Jarvis, OpenClaw와 다른 ingress가
같은 PostgreSQL 원장을 공유한다. 기존 Jarvis service account에는 `scm.publish` 권한을 추가해야
한다.
