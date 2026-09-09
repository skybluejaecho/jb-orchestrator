# ADR 0081: Credential 관리 이력은 append-only event 원장에 기록한다

## 상태

채택

## 배경

Credential의 최종 상태만 저장하면 누가 언제 발급하거나 폐기했는지 사후에 입증할 수 없다.
별도 감사 저장소는 transaction 정합성과 운영 복잡도를 늘리고, 모든 인증 성공을 이벤트로 남기면
일반 API 요청마다 영구 row가 생겨 불필요한 쓰기 부하가 발생한다.

## 결정

- 기존 `events` 원장에 `aggregate_type=service_account`로 감사 이벤트를 저장한다.
- Credential 발급, 개별 폐기, account 전체 폐기를 각각 별도 event type으로 기록한다.
- 이벤트에는 대상 credential ID, 만료 시각, actor account ID와 actor credential ID만 저장한다.
- Bearer token 원문과 digest는 이벤트에 저장하지 않는다.
- 상태 변경과 이벤트 append는 같은 Unit of Work에서 commit한다.
- 조회는 최신 sequence부터 반환하며 `before_sequence`와 `limit`으로 페이지를 이동한다.
- 일반 인증 성공은 `last_used_at`만 갱신하고 감사 이벤트를 추가하지 않는다.

## 결과

- 운영자는 credential rotation과 account 폐기의 수행 주체를 DB 원장에서 추적할 수 있다.
- API 인증 principal이 없는 bootstrap 변경은 actor가 null인 시스템 작업으로 구분된다.
- 기존 event 테이블을 재사용하므로 새 migration이나 별도 감사 저장소가 필요하지 않다.
- 도입 이전 credential에는 소급 발급 이벤트를 만들지 않으며, 이후 상태 변경부터 기록한다.
- 로그인 사용자와 외부 IdP subject 감사는 사용자 인증 경계를 도입할 때 확장한다.
