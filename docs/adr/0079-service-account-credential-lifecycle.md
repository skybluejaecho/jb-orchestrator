# ADR 0079: 서비스 계정 identity와 bearer credential 수명주기를 분리한다

## 상태

채택

## 배경

서비스 계정 row가 안정적인 권한 주체와 단 하나의 bearer token digest를 함께 소유하면 token을
교체하는 동안 구 credential과 새 credential을 동시에 허용할 수 없다. Jarvis, OpenClaw 같은
클라이언트가 서로 다른 host에서 독립적으로 갱신되는 구조에서는 무중단 rotation, 개별 만료,
유출 credential만의 폐기 및 실제 사용 시점 추적이 필요하다. 서비스 계정 자체를 복제하면
permission과 project scope가 갈라져 같은 논리 주체에 대한 정책 정합성이 약해진다.

## 결정

- `service_accounts`는 key, 이름, permission, project scope, 활성 상태를 가진 안정적인
  identity로 유지한다.
- bearer secret의 digest와 `created_at`, `expires_at`, `revoked_at`, `last_used_at`은 별도
  `service_account_credentials` 원장에 저장한다.
- 하나의 account는 여러 credential을 가질 수 있다. credential 폐기는 해당 secret만 막고,
  account 폐기는 소속 credential 전체의 인증을 막는다.
- token의 `jbsa_<uuid>.<secret>` 형식은 유지하되 UUID는 credential을 식별한다. 인증 성공 시
  principal에도 account ID와 credential ID를 함께 기록한다.
- credential 원문은 발급 시 한 번만 반환하고 DB에는 SHA-256 digest만 보관한다.
- 기존 token은 migration에서 account ID와 같은 credential ID로 backfill하여 재발급 없이
  계속 인증되도록 한다.
- downgrade는 account마다 정확히 하나의 비만료·비폐기 credential만 있을 때 허용한다.
  다중 credential이나 수명주기 상태를 잃게 되는 downgrade는 명시적으로 실패시킨다.
- credential 발급·목록·개별 폐기를 운영자가 수행하는 API와 CLI, rotation 정책 및 감사 화면은
  후속 변경에서 추가한다.

## 결과

- 클라이언트별 credential을 겹쳐 발급한 뒤 순차 교체하는 무중단 rotation 기반이 생긴다.
- permission과 project scope는 계속 account 한 곳에서 관리되어 credential 사이에 정책이
  갈라지지 않는다.
- 인증 성공마다 `last_used_at` 쓰기가 발생한다. 사용량이 커지면 비동기 집계나 갱신 간격 제한을
  별도 최적화할 수 있다.
- credential 관리 인터페이스가 추가되기 전에는 application service만 다중 발급과 개별 폐기를
  제공하며 기존 CLI는 최초 account/credential 발급과 account 전체 폐기를 유지한다.
