# ADR 0070: Jarvis는 알림 Delivery 원장을 관찰하고 명시적 복구 명령만 전달한다

## 배경

알림 구독과 Delivery는 Control Plane에 저장되고 Notification Worker가 실행하지만, 운영자가
상태와 Attempt를 확인하거나 복구 명령을 내리려면 API를 직접 호출해야 한다. Jarvis가 로컬 상태를
별도로 관리하거나 브라우저 타이머로 재시도하면 PostgreSQL 원장과 판단이 달라질 수 있다.

## 결정

- Jarvis는 선택한 프로젝트의 최근 Notification Delivery를 Control Plane에서 조회한다.
- 각 Delivery의 provider, 목적지 참조, 이벤트, 상태, 실패 분류, 시도 횟수와 다음 자동 재시도
  시각을 표시한다.
- Attempt 상세는 사용자가 펼칠 때 조회하며 최초, 수동, 자동, lease 복구 trigger와 Worker를
  표시한다. 내부 lease token은 Control Plane 응답 계약대로 노출하지 않는다.
- 실패 Delivery에는 기존 수동 재시도 명령을 제공한다.
- 자동 재시도가 예약된 Delivery에는 별도의 예약 취소 명령을 제공한다.
- 모든 쓰기 명령은 Jarvis server route가 보관한 서비스 계정 token으로 proxy하며 브라우저에
  token을 전달하지 않는다.
- Jarvis는 명령 응답 후 원장을 다시 조회하고, 알림 Domain Event를 수신하면 프로젝트 화면을
  갱신한다. 로컬에서 성공 상태를 추측하지 않는다.
- Jarvis 서비스 계정은 조회를 위한 `project.read`와 복구를 위한 `notification.manage` 권한을
  명시적으로 가진다.
- 구독 생성과 편집 UI는 별도 변경으로 분리한다.

## 결과

운영자는 하나의 프로젝트 화면에서 알림 전송과 복구 상태를 확인할 수 있고, Jarvis 외의 Control
Agent가 같은 API를 사용해도 PostgreSQL 원장을 기준으로 일관된 상태를 본다. 실제 전송과 자동
재시도 시점의 소유자는 계속 Notification Worker다.
