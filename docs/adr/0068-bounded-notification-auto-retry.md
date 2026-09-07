# ADR 0068: 재시도 가능한 알림 전송을 제한된 backoff로 다시 실행한다

## 배경

ORCH-070은 실패한 알림을 사람이 안전하게 재시도할 수 있게 했지만, 짧은 네트워크 단절이나
Webhook 서버의 일시 장애에도 운영자 개입이 필요하다. 반대로 모든 실패를 즉시 또는 무제한으로
재시도하면 수신 시스템을 압박하고 영구적인 설정 오류를 숨길 수 있다.

## 결정

- 자동 재시도는 Notification Worker의 명시적 옵션이며 기본 한도는 0으로 비활성화한다.
- `provider_unavailable`과 `timeout`만 재시도 가능 실패로 분류한다.
- `provider_rejected`, `unexpected`는 자동 재시도하지 않는다.
- `automatic_retry_limit`은 최초 시도 이후 허용할 자동 재시도 횟수이며 0에서 10 사이로 제한한다.
- 다음 실행 시각은 Delivery에 저장하여 Worker 재시작 뒤에도 예약을 유지한다.
- 지연은 `base_delay * 2^n`으로 증가하고 설정된 최대 지연을 넘지 않는다.
- 예약 시간이 되기 전에는 Delivery를 claim할 수 없다.
- 예약 시간이 되면 동일 Delivery와 idempotency key로 다시 claim하고 `automatic` Attempt를 만든다.
- 각 실패 Attempt에는 당시의 재시도 가능 여부를 함께 보존한다.
- 한도를 소진하거나 재시도 불가능한 실패는 terminal failed 상태로 남긴다.
- 예약 시 `notification.delivery_retry_scheduled` Domain Event를 실패 이벤트 다음에 기록한다.
- 명시적 수동 재시도는 저장된 자동 재시도 예약과 한도를 제거하고 즉시 `pending`으로 전환한다.

## 결과

일시적인 외부 장애는 전송 identity와 모든 Attempt 증거를 유지한 채 자동 복구할 수 있다. 기본
설정은 기존 수동 운영과 완전히 동일하며, Worker별 명시적 옵션을 사용한 경우에만 자동 재시도가
활성화된다. 프로젝트별 정책과 자동 재시도 취소 API는 후속 변경으로 분리한다.
