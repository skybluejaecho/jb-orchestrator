# ADR 0073: Jarvis 알림 운영 화면은 필터와 비차단 Provider 진단을 제공한다

## 배경

Delivery와 Subscription이 늘어나면 최근 10개를 시간순으로만 표시하는 화면에서는 실패나 예약된
재시도를 찾기 어렵다. 또한 유효한 provider key라도 이를 지원하는 Notification Worker가 현재
없으면 구독은 저장되지만 Delivery가 처리되지 않는다. 반대로 Worker 상태 때문에 구독 등록을
막으면 계획된 배포나 일시적인 재시작 중 설정을 미리 준비할 수 없다.

## 결정

- Delivery API proxy는 최대 200개를 조회하고 검증된 상태 필터를 Control Plane에 전달한다.
- 화면은 상태, provider와 이벤트 필터를 제공한다.
- 자동 재시도 예약, 일반 실패, 처리 중, 대기, 성공 순으로 운영 중요도를 우선한다.
- Notification Worker presence의 kind와 capability를 provider key에 대조한다.
- 지원하는 온라인 Worker, 지원 Worker의 응답 지연·종료, 지원 Worker 없음 상태를 구분한다.
- Provider 진단은 경고만 제공하며 구독 생성이나 설정 변경을 차단하지 않는다.
- Worker 상태는 30초마다 갱신하고 기존 `/api/workers` 서버 proxy와 서비스 계정 경계를 재사용한다.
- Worker 현황판은 `notification`과 `readiness_monitor` kind를 명시적인 한글 라벨로 표시한다.
- Provider와 이벤트 필터링, 중요도 정렬 및 Worker 지원 판정은 순수 정책 함수로 분리해 테스트한다.

## 결과

운영자는 장애와 예약된 복구를 먼저 확인하면서 필요한 범위로 Delivery를 좁힐 수 있다. Provider
오타나 Worker 배포 누락을 구독 시점에 발견할 수 있지만, Control Plane의 느슨하게 결합된 구성과
사전 설정 가능성은 유지된다.
