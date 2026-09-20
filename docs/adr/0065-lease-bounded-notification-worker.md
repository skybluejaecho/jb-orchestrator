# ADR 0065: 알림 전송을 설치형 Provider와 lease 기반 Worker로 실행한다

## 배경

Notification outbox에는 외부로 전달할 불변 intent가 저장되지만 이를 안전하게 소비하는 실행
경계가 없었다. API나 readiness monitor가 직접 네트워크 전송까지 담당하면 외부 장애가 core
transaction에 결합되고, 여러 프로세스가 같은 알림을 동시에 처리할 위험이 있다.

## 결정

- 별도 `jb-notification-worker` 프로세스가 pending Delivery를 소비한다.
- Provider는 `jb_orchestrator.notification_providers` Python entry-point에 no-argument factory로
  등록한다. core는 특정 Webhook SDK나 자격증명을 알지 않는다.
- Worker는 자신에게 설치된 provider key별로 가장 오래된 Delivery 하나를 PostgreSQL
  `FOR UPDATE SKIP LOCKED`로 claim한다.
- claim에는 worker id, 무작위 lease token, 만료 시각과 attempt count를 기록한다.
- Provider 호출 timeout은 lease보다 짧아야 한다. 프로세스가 비정상 종료되면 만료된 claim을
  다른 Worker가 새 lease token으로 회수한다.
- 완료와 실패는 현재 lease token 소유자만 기록한다. 이미 외부 전송 후 Worker가 종료될 수
  있으므로 전송 보장은 at-least-once이며 Provider에는 안정적인 idempotency key를 전달한다.
- 성공 시 provider-neutral output을, 실패 시 설명과 안정적인 failure code를 원장에 저장한다.
- 실패 Delivery는 이번 단계에서 terminal이다. 자동/수동 재시도 정책은 별도 기능으로 확장한다.
- Worker presence에는 `notification` kind와 설치된 provider key들을 capability로 기록한다.

## 결과

Jarvis나 특정 Control Agent가 실행 주체가 아니어도 PostgreSQL outbox를 기준으로 알림을
처리할 수 있다. 여러 Worker의 수평 실행과 비정상 종료 복구가 가능하고, 실제 Webhook 같은
전송 구현은 독립 package로 설치할 수 있다. 외부 서비스는 중복 가능성을 idempotency key로
억제해야 한다.
