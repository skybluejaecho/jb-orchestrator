# ADR 0072: Jarvis 알림 운영 경계를 실제 프로세스 스모크에 포함한다

## 배경

기존 시스템 스모크는 Notification Worker와 Webhook Provider를 실행했지만 구독, Delivery,
Attempt와 복구 명령은 Control Plane API에 직접 요청했다. 따라서 ORCH-073과 ORCH-074에서 추가한
Jarvis server proxy의 인증, 필드 변환과 프로젝트 범위가 실제 프로세스 사이에서도 동작하는지는
mock 기반 계약 테스트로만 확인됐다.

## 결정

- 스모크용 Jarvis 서비스 계정에 `notification.manage` 권한을 명시적으로 부여한다.
- 알림 구독 생성, 목록 조회와 이벤트 필터 설정은 실행 중인 Jarvis HTTP route를 통해 수행한다.
- Delivery 목록과 Attempt 이력도 Jarvis route를 통해 조회한다.
- Notification Worker는 첫 Webhook 장애에 장기 backoff 자동 재시도를 예약한다.
- Jarvis route를 통해 예약을 취소한 뒤 같은 Delivery를 즉시 수동 재시도한다.
- 최종적으로 두 readiness 이벤트가 모두 전송되고, 실패 및 성공 Attempt가 보존되며, API 응답에
  lease token이 없는지 검증한다.
- 실제 Vinext 콜드 스타트가 30초를 넘을 수 있으므로 기본 프로세스 준비 제한을 60초로 늘린다.
  사용자는 CLI 옵션으로 이 값을 계속 조정할 수 있다.
- 검증은 빈 일회용 PostgreSQL 데이터베이스에서만 실행한다.

## 결과

Jarvis, Control Plane, PostgreSQL, Notification Worker와 Webhook Provider가 하나의 자동화된
인수 경계로 검증된다. 브라우저용 프록시의 권한이나 payload 변환이 어긋나면 배포 전 시스템
스모크에서 발견되며, 느린 콜드 스타트 때문에 정상 기능이 간헐적으로 실패할 가능성도 줄어든다.
