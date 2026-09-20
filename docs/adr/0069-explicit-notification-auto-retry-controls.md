# ADR 0069: 예약된 알림 자동 재시도를 명시적으로 취소한다

## 배경

ORCH-071은 일시적인 알림 전송 실패를 제한된 backoff로 다시 실행한다. 그러나 운영자가 장애
원인을 확인해 외부 호출을 중단하려는 경우, 예약을 제거할 Control Plane 명령이 없다. 화면에서만
예약을 숨기면 다른 클라이언트와 Notification Worker는 계속 저장된 일정을 따르게 된다.

## 결정

- `POST /v1/projects/{project_id}/notification-deliveries/{delivery_id}/automatic-retry/cancel`은
  실패 Delivery의 자동 재시도 예약을 제거한다.
- 취소는 `next_attempt_at`을 비우고 자동 재시도 한도를 0으로 만들지만 상태, 실패 코드, 재시도
  가능 여부, 실패 이유와 누적 시도 횟수는 보존한다.
- 이미 예약이 없는 실패에 대한 반복 취소는 같은 Delivery를 반환하고 새 이벤트를 만들지 않는다.
- 성공 또는 pending/claimed 상태에는 취소할 예약이 없으므로 충돌로 처리한다.
- 프로젝트 scope를 검증하고 기존 `notification.manage` 권한으로 명령을 제한한다.
- row lock을 사용하여 예약 취소와 Notification Worker의 claim 중 하나만 먼저 확정되게 한다.
- 취소 성공은 수행 계정을 포함한 `notification.delivery_automatic_retry_cancelled` 이벤트로
  감사한다.
- 예약된 실패에 기존 수동 retry API를 호출하면 예약을 제거하고 즉시 `pending`으로 전환한다.

## 결과

자동 복구는 운영자가 언제든 중단할 수 있는 선택적 정책으로 유지된다. 취소 후에도 실패와 Attempt
증거는 보존되며, 필요하면 기존 수동 재시도 API로 같은 Delivery를 즉시 다시 실행할 수 있다.
Jarvis와 다른 Control Agent는 저장된 상태와 이벤트를 동일한 기준으로 관찰할 수 있다.
