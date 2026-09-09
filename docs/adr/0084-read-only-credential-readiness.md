# ADR 0084: Credential readiness는 읽기 전용 운영 진단으로 계산한다

## 상태

채택

## 배경

ADR 0083의 서비스 계정 inventory는 운영자가 credential 수와 수명주기 상태를 확인하게 하지만,
어떤 account가 곧 인증 불능이 되는지 직접 계산해야 한다. 각 클라이언트가 서로 다른 기준으로
판정하면 같은 원장에서도 운영 상태가 달라지고, 진단 과정에 자동 rotation이나 폐기를 결합하면
조회가 예기치 않은 상태 변경과 외부 secret 교체를 일으킬 수 있다.

## 결정

- `GET /v1/service-accounts/readiness`는 모든 판정에 하나의 UTC inspection 시각을 사용한다.
- 상태는 `healthy`, `expiring_soon`, `expired`, `no_usable_credential`,
  `account_disabled`로 제한한다.
- 판정 우선순위는 account 비활성, usable credential 부재와 만료 이력, usable credential 부재,
  가장 가까운 활성 credential의 경고 기간 진입, 정상 순이다.
- `next_expires_at`은 활성 credential 중 가장 가까운 만료 시각이며 비만료 credential만 있으면
  null이다. Credential 집계 의미는 ADR 0083과 동일하다.
- 기본 경고 기간은 `JB_CREDENTIAL_EXPIRY_WARNING_SECONDS`로 설정하고 604800초를 사용한다.
  API와 CLI는 1초부터 1년까지 요청별 override를 허용한다.
- 목록은 account key 순서의 `key_prefix`, `after_key`, `limit`과 `issues_only`를 지원한다.
  `issues_only`는 최대 500개씩 DB page를 읽으며 요청 limit에 도달하면 중단한다.
- Route는 기존 inventory와 같이 API 인증이 켜져 있어야 하며 `project.admin` permission과
  `all_projects` scope를 모두 요구한다.
- 응답은 account inventory와 판정 근거 시각만 포함하고 token 원문과 digest는 반환하지 않는다.
- 진단은 credential 발급·폐기, account 활성화, 알림 전송을 수행하지 않는다.

## 결과

- Control Plane이 저장된 account와 credential 원장을 기준으로 일관된 운영 판정을 제공한다.
- 운영자는 `jb auth doctor --issues-only`로 조치가 필요한 account만 발견하고 기존 rotation
  절차를 명시적으로 실행할 수 있다.
- 전체 inventory를 메모리에 올리지 않지만, 건강한 account가 많을 때 issue-only 요청은 결과를
  채우기 위해 여러 bounded page를 조회할 수 있다.
- 자동 rotation, secret store 갱신, notification 연계와 정책별 경고 기간은 후속 범위로 남긴다.
