# ADR 0067: Notification Delivery의 각 claim과 수동 복구를 별도 원장으로 기록한다

## 배경

Delivery의 `attempt_count`와 마지막 결과만으로는 최초 전송 실패, lease 만료 후 회수, 운영자
재시도를 각각 감사할 수 없다. 실패한 Delivery가 terminal인 상태에서는 일시적인 Webhook
장애가 해소되어도 같은 불변 전송 의도를 다시 실행할 방법도 없다.

## 결정

- `notification_delivery_attempts`는 Delivery별 단조 증가 attempt number를 가진다.
- 각 claim은 `initial`, `manual`, `lease_recovery` trigger, worker id, 내부 lease token, 시작 시각을
  기록한다.
- 성공과 실패 시 해당 Delivery와 현재 Attempt를 같은 transaction에서 종료한다.
- lease가 만료된 claim을 회수하면 기존 Attempt를 `lease_expired` 실패로 먼저 닫고 새 Attempt를
  시작한다.
- Attempt 조회 응답에는 동시성 제어용 lease token을 포함하지 않는다.
- 실패한 Delivery는 프로젝트 scope와 `notification.manage` 권한이 확인된 명시적 API 요청으로만
  `pending`에 되돌린다.
- 재시도는 Delivery ID, source event, destination snapshot, payload와 idempotency key를 변경하지
  않고 이전 attempt evidence도 보존한다.
- pending 또는 claimed Delivery에 대한 반복 retry 요청은 현재 상태를 반환한다. succeeded
  Delivery는 재시도할 수 없다.
- retry actor와 상태 전이는 Domain Event로 감사한다.
- 자동 재시도와 backoff는 이번 결정에 포함하지 않는다.

## 결과

운영자는 네트워크 장애의 각 전송 시도를 잃지 않고 확인할 수 있으며, 외부 시스템의
idempotency 계약을 유지한 채 동일 Delivery를 복구할 수 있다. 다음 자동 재시도 정책은 이
Attempt 원장과 안정적인 failure code 위에 추가할 수 있다.
