# ADR 0080: Credential rotation은 인증된 Control Plane 관리 경계로 수행한다

## 상태

채택

## 배경

ADR 0079는 한 서비스 계정이 여러 bearer credential을 가질 수 있는 수명주기 원장을 만들었지만
운영 인터페이스는 제공하지 않았다. 원격 Jarvis와 OpenClaw credential을 교체하려면 새 token을
발급하고 두 token의 중첩 기간 동안 연결을 검증한 뒤 구 token만 폐기할 수 있어야 한다. 이 작업을
DB 직접 접근으로만 제공하면 원격 운영 자동화가 어렵고 API 권한 경계를 우회하게 된다. 반대로
최초 관리 계정까지 API로 발급하려 하면 아직 인증 주체가 없는 bootstrap 순환이 생긴다.

## 결정

- `POST /v1/service-accounts/{account_id}/credentials`는 선택적인 만료 시각을 가진 credential을
  발급하고 bearer token 원문을 한 번만 반환한다.
- `GET /v1/service-accounts/{account_id}/credentials`는 생성·만료·폐기·마지막 사용·활성 상태만
  반환한다. Token 원문과 digest는 어떤 목록 응답에도 포함하지 않는다.
- `DELETE /v1/service-accounts/{account_id}/credentials/{credential_id}`는 경로의 account에 실제로
  속한 credential만 폐기한다. Account 자체와 다른 credential은 계속 활성 상태를 유지한다.
- 모든 credential 관리 route에는 `project.admin` permission과 `all_projects` scope를 모두
  요구한다. API 인증이 비활성화된 경우 route는 사용 불가로 닫힌다.
- `jb auth credential issue|list|revoke`는 `JB_CONTROL_PLANE_URL`과 `JB_API_TOKEN`을 사용해 위 API를
  호출한다. 최초 서비스 계정 발급을 위한 `jb auth issue`는 bootstrap 용도로 DB 경계를 유지한다.
- 권장 rotation 순서는 새 credential 발급, 대상 클라이언트 secret 교체, 새 token 연결 검증,
  구 credential 폐기다.

## 결과

- Jarvis와 OpenClaw를 중단하지 않고 credential을 순차 교체할 수 있다.
- 일반 project-scoped 서비스 계정은 credential metadata 조회나 rotation을 수행할 수 없다.
- 운영자 token은 모든 프로젝트 범위를 가진 강한 credential이므로 별도 secret 저장소에서 관리하고
  일상적인 worker·client token으로 재사용하지 않아야 한다.
- 서비스 계정 생성, permission 변경, account 목록과 감사 이력은 이번 관리 경계에 포함하지 않으며
  별도 요구가 생길 때 확장한다.
