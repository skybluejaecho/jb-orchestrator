# ADR 0064: 알림 구독과 Delivery intent를 PostgreSQL 원장으로 관리한다

## 배경

Worker readiness 경보는 서버에서 생성되고 프로젝트 이벤트로 남지만 외부 시스템이 어떤
전환을 받아야 하는지, 전송이 필요한 이벤트가 무엇인지 영속적으로 표현하지 않았다. 특정
Webhook이나 OpenClaw 구현을 경보 서비스에 직접 연결하면 네트워크 실패가 경보 transaction을
중단시키고 core가 공급자 자격증명을 소유하게 된다.

## 결정

- 프로젝트별 Notification Subscription은 provider key, opaque destination reference, 구독할
  이벤트 종류와 활성 상태를 저장한다.
- 지원 이벤트는 `worker.readiness_alerted`, `worker.readiness_critical`,
  `worker.readiness_resolved`로 제한한다. reason 변경은 별도 외부 알림을 만들지 않는다.
- destination reference는 Adapter가 해석할 식별자이며 URL, token 또는 secret 원문을 저장하지
  않는다. 공급자 자격증명은 이후 Adapter 실행 환경이 소유한다.
- 같은 프로젝트, provider와 destination reference 조합은 하나만 등록할 수 있다.
- 구독 생성과 설정 변경은 프로젝트 이벤트로 감사하며 `notification.manage` 권한을 요구한다.
- 구독 및 Delivery 조회에는 기존 `project.read` 권한과 프로젝트 scope를 적용한다.
- 지원되는 readiness 이벤트를 기록하는 transaction에서 활성 구독마다 Notification Delivery를
  함께 생성한다.
- Delivery는 생성 시점의 provider, destination reference, payload와 idempotency key를 복사하여
  이후 구독 변경과 독립적인 전송 의도로 보존한다.
- 동일한 subscription과 source event 조합은 하나의 Delivery만 만들며 상태는 `pending`으로
  시작한다.
- 새 구독은 생성 이후 발생하는 이벤트에만 적용하며 과거 이벤트를 자동 backfill하지 않는다.
- 구독 비활성화는 미래 Delivery 생성을 중단하지만 이미 생성된 Delivery를 취소하거나 삭제하지
  않는다.
- `claimed`, `succeeded`, `failed` 상태는 다음 Notification Worker 계약을 위해 스키마에 포함하되
  이번 단계에서는 실제 claim이나 네트워크 전송을 수행하지 않는다.

## 결과

경보 원장과 “외부로 보내야 할 내용”이 같은 PostgreSQL transaction에서 확정된다. Jarvis나
브라우저가 열려 있지 않아도 전송 의도는 유실되지 않으며, 공급자 장애가 경보 평가를 직접
중단시키지 않는다. 다음 단계의 Worker와 Adapter는 pending Delivery만 처리하면 되고 core는
특정 알림 공급자나 secret 형식에 종속되지 않는다.
