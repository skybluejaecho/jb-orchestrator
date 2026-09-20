# ADR 0082: Credential rotation은 프로세스 수준 시스템 스모크에서 검증한다

## 상태

채택

## 배경

ADR 0079부터 ADR 0081까지 서비스 계정 identity와 credential의 분리, 인증된 rotation API,
append-only 감사 원장을 구현했다. 단위 및 API 계약 테스트만으로는 실제 Control Plane 프로세스와
PostgreSQL을 통과한 새 token이 인증되고 폐기된 token이 즉시 거부되는지 입증할 수 없다. 이 경계가
깨지면 개별 기능 검사는 통과해도 원격 Jarvis나 OpenClaw의 무중단 rotation이 배포 환경에서 실패할
수 있다.

## 결정

- 기존 release system smoke의 관리용 서비스 계정을 rotation 대상으로 재사용한다.
- 실행 중인 Control Plane API에서 기존 credential로 replacement credential을 발급한다.
- replacement token으로 보호된 API를 호출해 인증 성공을 먼저 확인한다.
- replacement credential로 기존 credential을 폐기하고 기존 token이 즉시 `401`로 거부되는지
  확인한다.
- credential 목록에서 기존 credential은 inactive, replacement는 active인지 검증한다.
- 최신 감사 이벤트에서 replacement 발급 actor는 기존 credential, 기존 credential 폐기 actor는
  replacement credential인지 검증한다.
- 구조화된 smoke 결과에는 account와 credential ID 및 검증 상태만 포함하고 bearer token은
  포함하지 않는다.

## 결과

- 실제 PostgreSQL, 인증 middleware, application service와 HTTP schema를 지나는 rotation 경계가
  release readiness에 포함된다.
- 새 token을 확인하기 전에 기존 token을 폐기하는 잘못된 운영 순서를 smoke가 사용하지 않는다.
- credential secret이나 digest를 CI 출력에 노출하지 않고도 rotation 결과를 추적할 수 있다.
- 만료 credential의 시간 경계와 외부 secret store 교체 자동화는 이 변경에 포함하지 않는다.
