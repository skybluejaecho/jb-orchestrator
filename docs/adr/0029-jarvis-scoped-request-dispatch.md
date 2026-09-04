# ADR 0029: Jarvis 요청 제출을 별도 권한으로 제한한다

## 상태

승인됨

## 배경

관찰 전용 Jarvis에서 사용자가 선택한 프로젝트에 작업 요청을 제출할 필요가 있다. Jarvis가
Workflow나 DB를 직접 조작하면 다른 입력 어댑터와 실행 규칙이 달라지고, 네트워크 응답 유실
후 재시도할 때 같은 작업이 중복 실행될 수 있다. 요청 제출을 추가한다는 이유로 승인이나 취소
권한까지 함께 부여해서도 안 된다.

## 결정

- Jarvis는 Control Plane의 `POST /v1/projects/{project_id}/dispatches`만 호출한다.
- server route가 bearer token을 보관하고 ingress를 `jarvis`로 고정한다.
- 브라우저는 입력별 idempotency key를 만들고 실패한 동일 입력을 재시도할 때 이를 유지한다.
- 제목이나 요청 내용이 바뀌면 기존 key를 폐기하고 새 요청으로 취급한다.
- Jarvis 서비스 계정에는 `project.read`, `request.dispatch`, `all_projects`만 부여한다.
- 승인과 취소는 이번 증분에 포함하지 않는다.
- 사용자 인증 계층이 추가되기 전까지 Jarvis는 로컬 전용으로 유지한다.

## 결과

Jarvis, OpenClaw, CLI는 모두 같은 request dispatch application service를 사용한다. 실행 주체가
달라도 요청, Run, Workflow 상태는 같은 PostgreSQL 원장에 기록된다. 이후 승인 UI는
`workflow.approve` 권한과 명시적 확인 절차를 갖춘 별도 증분으로 추가할 수 있다.
