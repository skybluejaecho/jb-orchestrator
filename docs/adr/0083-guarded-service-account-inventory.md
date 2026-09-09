# ADR 0083: 서비스 계정 운영 현황은 읽기 전용 global admin 경계로 제공한다

## 상태

채택

## 배경

Credential 관리 API가 account ID를 요구하지만 운영자가 등록된 account를 발견하고 권한·scope와
credential 상태를 함께 확인할 방법이 없었다. DB에 직접 접근하면 원격 운영 경계를 우회하고,
credential 원장을 그대로 반환하면 digest 같은 secret-derived 값이 노출될 수 있다. 또한 비활성
account가 만료되지 않은 credential을 보유한 경우 credential 수명주기만 보고 실제 인증 가능 상태로
오해할 수 있다.

## 결정

- `GET /v1/service-accounts`는 key 오름차순으로 account 운영 현황을 반환한다.
- 목록은 `enabled`, `key_prefix`, `after_key`, `limit`으로 필터와 cursor 페이지네이션을 제공한다.
- `GET /v1/service-accounts/{account_id}`는 동일한 표현으로 하나의 account를 조회한다.
- 두 route는 API 인증이 활성화된 경우에만 열리고 `project.admin` permission과 `all_projects`
  scope를 모두 요구한다.
- Account 표현은 안정적인 ID, key, 이름, permission, project scope, 활성 상태와 생성 시각을 포함한다.
- Credential 요약은 전체, active, usable, expired, revoked 수와 최신 발급·사용 시각만 포함한다.
- `active`는 폐기되지 않고 아직 만료되지 않은 credential 수다. `usable`은 account도 활성화된 경우의
  active 수다. `expired`는 폐기되지 않은 만료 credential만 세어 active·expired·revoked가 전체를
  분할하도록 한다.
- Token 원문과 digest는 목록, 상세, 집계 어디에도 포함하지 않는다.
- `jb auth account list|show`는 Control Plane API를 호출하며 DB에 직접 접근하지 않는다.

## 결과

- 운영자는 account ID를 사전에 보유하지 않아도 credential rotation 대상을 발견할 수 있다.
- Account 비활성화와 credential 자체 상태를 구분해 실제 인증 가능성을 판단할 수 있다.
- 목록 페이지의 credential은 한 번의 bulk repository 조회로 집계하여 account별 N+1 조회를 피한다.
- Account 발급, 이름·permission·scope 변경, 재활성화와 자동 credential rotation은 이 변경에
  포함하지 않는다.
