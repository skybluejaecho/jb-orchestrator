# Webhook notification provider

이 package는 `jb_orchestrator.notification_providers`의 `webhook` entry point를 제공한다.
Notification Worker가 전달한 불변 event snapshot을 범용 JSON `POST`로 전송한다.

## 설정

실제 endpoint와 선택적 HMAC secret은 DB가 아니라 Worker 환경에서 opaque destination
reference별로 설정한다.

```powershell
$env:JB_WEBHOOK_DESTINATIONS='{
  "ops-primary": {
    "url": "https://hooks.example.com/jb-events",
    "signing_secret": "replace-with-secret"
  }
}'
```

선택 설정:

```text
JB_WEBHOOK_HTTP_TIMEOUT_SECONDS=10
```

`JB_WEBHOOK_ALLOW_INSECURE_LOOPBACK=true`는 process smoke 전용이다. 이 값은
`JB_ENVIRONMENT=test`이면서 loopback HTTP endpoint인 경우에만 허용된다.

## 실행

```powershell
uv run --with-editable . --with-editable adapters/webhook `
  jb-notification-worker --list-providers

uv run --with-editable . --with-editable adapters/webhook `
  jb-notification-worker
```

## 전송 계약

- `Content-Type: application/json`
- `Idempotency-Key`: 영속 Delivery의 안정적인 중복 억제 key
- `X-JB-Delivery-ID`: Delivery UUID
- `X-JB-Event-Type`: 원본 event type
- `X-JB-Signature-256`: signing secret이 설정된 경우 exact body의 HMAC-SHA256

성공 응답은 모든 `2xx`다. `408`, `429`, `5xx`와 transport 오류는
`provider_unavailable`, 나머지 non-2xx는 `provider_rejected`로 기록한다. Endpoint URL,
secret, 응답 본문은 결과나 오류 원장에 저장하지 않는다.
