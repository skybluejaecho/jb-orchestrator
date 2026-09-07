# ADR 0066: 범용 Webhook Provider의 endpoint와 secret은 Adapter 환경이 소유한다

## 배경

Notification Worker는 설치형 Provider를 실행할 수 있지만 실제 외부 전송 구현은 없었다.
Webhook URL이나 signing secret을 Subscription에 직접 저장하면 프로젝트 조회 권한을 가진
사용자에게 자격증명이 노출되고 core가 특정 외부 서비스의 secret 수명주기를 소유하게 된다.

## 결정

- `adapters/webhook` 독립 package가 `webhook` notification provider entry point를 제공한다.
- Subscription과 Delivery에는 `destination_ref`만 저장한다. Worker 환경의
  `JB_WEBHOOK_DESTINATIONS`가 reference를 endpoint URL과 선택적 signing secret으로 해석한다.
- 전송 본문은 delivery, project, event, idempotency 정보와 불변 event payload를 포함하는
  canonical JSON envelope다.
- 모든 요청에 `Idempotency-Key`, `X-JB-Delivery-ID`, `X-JB-Event-Type`을 전달한다.
- signing secret이 있으면 exact body의 HMAC-SHA256을 `X-JB-Signature-256`으로 전달한다.
- production endpoint는 HTTPS만 허용한다. loopback HTTP 예외는 `JB_ENVIRONMENT=test`에서
  명시적으로 활성화한 process smoke에만 허용한다.
- 모든 2xx를 성공으로 처리하고 status code와 선택적 request id만 결과로 저장한다. endpoint,
  secret과 response body는 로그 또는 원장에 포함하지 않는다.
- 408, 429, 5xx와 transport 오류는 `provider_unavailable`, 그 외 non-2xx와 미등록 reference는
  `provider_rejected`로 분류한다.
- Delivery 조회 API는 내부 동시성 제어 값인 lease token을 노출하지 않는다.

## 결과

OpenClaw, 사내 서비스 또는 변환 gateway는 동일한 서명 JSON 계약으로 readiness event를 받을
수 있다. 운영자는 core DB 변경 없이 Worker 환경에서 endpoint와 secret을 교체할 수 있다.
Slack이나 Discord 고유 payload가 필요하면 같은 Provider port를 구현하는 별도 adapter를
추가한다.
