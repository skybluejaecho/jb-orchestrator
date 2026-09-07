# ADR 0071: Jarvis는 Provider 중립적인 알림 구독 설정만 관리한다

## 배경

ORCH-073은 Jarvis에서 Delivery와 Attempt를 관찰하고 복구할 수 있게 했지만, 구독을 만들거나
이벤트 필터를 변경하려면 API를 직접 호출해야 한다. 실제 Webhook URL과 서명 Secret을 브라우저나
Control Plane에 입력하게 만들면 ORCH-069의 Worker 소유 보안 경계를 훼손한다.

## 결정

- Jarvis는 선택한 프로젝트의 Notification Subscription 목록을 Control Plane에서 조회한다.
- 사용자는 provider key, 불투명한 destination reference와 지원 이벤트를 선택해 구독을 등록한다.
- Jarvis는 provider key를 `webhook`에 고정하지 않고 설치형 Provider가 사용하는 유효한 키를
  전달한다.
- 지원 이벤트는 Worker readiness 경보 생성, 긴급 전환과 해소로 제한한다.
- 기존 구독은 이벤트 필터를 변경하거나 활성화·비활성화할 수 있다.
- 이벤트 필터는 비어 있을 수 없으며 Jarvis server route와 Control Plane이 각각 검증한다.
- 실제 endpoint URL, 인증 정보와 서명 Secret은 계속 Notification Worker 환경만 소유한다.
- 브라우저에는 Jarvis 서비스 계정 token을 전달하지 않으며 모든 변경은 `notification.manage`
  권한으로 proxy한다.
- 구독 Domain Event를 수신하면 Jarvis는 로컬 상태를 확정하지 않고 Control Plane 원장을 다시
  조회한다.

## 결과

운영자는 Jarvis에서 알림 목적지와 이벤트 범위를 조정할 수 있지만 외부 전송 자격 증명에는
접근하지 않는다. 새 Provider를 설치해도 Control Plane과 Jarvis 계약을 변경하지 않고 provider
key와 Worker-side destination resolver를 추가해 사용할 수 있다.
