# ADR 0024: API 접근을 서비스 계정과 프로젝트 범위로 제한한다

## 상태

승인됨

## 배경

Jarvis, OpenClaw, CLI 같은 입력 어댑터가 동일한 Control Plane API를 호출할 수 있지만,
요청 출처 헤더는 인증 정보가 아니다. 특히 OpenClaw가 원격 서버에서 접속할 때 하나의
공유 관리자 secret만 사용하면 프로젝트 간 격리와 최소 권한 원칙을 지킬 수 없다.

## 결정

- API 호출 주체는 DB에 저장되는 `ServiceAccount`로 식별한다.
- 발급한 bearer token 원문은 한 번만 출력하고 DB에는 SHA-256 digest만 저장한다.
- 각 서비스 계정은 명시적인 permission과 `project_ids` 또는 `all_projects` 범위를 가진다.
- permission은 조회, 요청 dispatch, workflow 승인, run 취소, 프로젝트 관리로 분리한다.
- `/v1` 전체에 bearer 인증을 적용하고 health endpoint는 인증 없이 제공한다.
- 직접 또는 간접 resource가 속한 프로젝트를 DB 관계로 확인한 후 scope를 검사한다.
- 프로젝트가 특정되지 않는 전역 catalog/list API는 `all_projects` 계정만 호출할 수 있다.
- 인증 기능은 로컬 호환성을 위해 기본적으로 비활성화하지만, loopback이 아닌 주소에
  바인딩할 때는 반드시 활성화해야 한다.
- CLI client는 `JB_API_TOKEN`을 설정하면 모든 Control Plane 요청에 token을 전달한다.

## 결과

OpenClaw와 Jarvis는 서로 다른 계정과 권한을 사용할 수 있다. 예를 들어 사용자 요청을
전달하는 OpenClaw Control Agent에는 특정 프로젝트의 `project.read`와
`request.dispatch`만 주고, task를 실행하는 Worker에는 dispatch 권한을 주지 않을 수 있다.
Token 폐기는 즉시 다음 요청부터 적용된다.

현재 token은 만료 시간이 없는 장기 credential이다. 자동 rotation, 감사 로그, 사용자
로그인/OIDC는 별도 후속 작업으로 확장한다.
