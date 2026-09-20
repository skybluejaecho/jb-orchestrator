# ADR 0032: Jarvis 실행 취소에 식별자 확인 절차를 둔다

## 상태

승인됨

## 배경

Workflow 실행 취소는 선택한 Workflow만 화면에서 숨기는 동작이 아니다. Control Plane은
활성 노드를 중단하고 연결된 Run과 열린 User Request를 함께 취소하며 남은 예산 예약을
해제한다. Worker가 외부 executor를 실행 중이면 lease 소유권 상실을 감지한 뒤 provider 취소
hook도 호출한다. 따라서 목록의 단일 클릭으로 실행을 취소하면 잘못된 실행을 중단할 위험이
크다.

## 결정

- 취소 동작은 사용자가 선택한 실행의 상세 화면에만 표시한다.
- `pending`, `running`, `awaiting_approval` 상태에서만 취소 진입점을 표시한다.
- 최종 취소 버튼은 `취소 {execution-id 앞 8자리}` 문구를 정확히 입력해야 활성화하며 Jarvis
  server route도 같은 문구를 검증한 뒤에만 Control Plane을 호출한다.
- browser는 실행 ID와 확인 문구만 Jarvis server route에 보내고, server route가
  `run.cancel` 권한을 가진 token으로 해당 Workflow 실행의 취소 API를 호출한다.
- Jarvis는 낙관적으로 상태를 변경하지 않는다. 성공 응답 뒤 상세와 프로젝트 overview를 다시
  조회하고 이후 SSE 이벤트에도 재조회한다.
- 다른 actor가 먼저 실행을 끝낸 경합은 Control Plane의 `409 Conflict`를 그대로 표시한다.
- token과 실제 lifecycle 전이 규칙은 browser나 Jarvis에 복제하지 않는다.

## 결과

사용자는 영향을 확인하고 대상 실행을 식별한 뒤에만 취소할 수 있다. Control Plane이 전체
실행 계층과 예산의 일관성을 계속 책임지며 Jarvis는 일시적인 조작 화면으로 남는다. 다만 현재
서비스 계정 방식은 실제 취소 사용자를 구분하지 않으므로 외부 공개 전에 사용자 인증과 actor
감사 기록이 필요하다.
