# ADR 0031: Jarvis 승인 결정을 실행 상세에 명시적으로 둔다

## 상태

승인됨

## 배경

Jarvis는 최근 Workflow 목록만 보여주므로 사용자는 어떤 노드가 왜 멈췄는지, 이전 단계에서
무엇이 생성됐는지 확인할 수 없다. 승인 기능만 목록에 바로 추가하면 충분한 실행 문맥 없이
Workflow 경로를 변경할 위험이 있다. 반대로 Jarvis가 실행 상태를 별도로 저장하면 Control
Plane의 PostgreSQL 원장과 서로 다른 현재 상태가 생길 수 있다.

## 결정

- 목록에서 사용자가 선택한 실행만 Control Plane의 실행 상세와 산출물 API로 조회한다.
- Jarvis는 조회 결과를 영속화하지 않고 SSE 이벤트 뒤에 다시 조회한다. Control Plane이 계속
  유일한 진실의 원천이다.
- `awaiting_approval` 노드에만 승인과 반려 동작을 표시한다.
- 승인 또는 반려를 선택한 뒤 별도의 확정 동작을 요구한다. 결정은 Workflow 그래프의 다음
  경로를 즉시 활성화할 수 있기 때문이다.
- browser는 Jarvis server route만 호출한다. server route가 `workflow.approve` 권한을 가진
  전용 서비스 계정 token으로 Control Plane 요청을 대리한다.
- 동시 처리로 이미 상태가 바뀐 경우 Control Plane의 `409 Conflict`를 사용자에게 표시하고
  상세를 다시 조회할 수 있게 한다.
- 실행 취소는 권한과 영향 범위가 다른 후속 기능으로 분리한다.

## 결과

사용자는 승인 전에 노드 실행 결과와 산출물을 같은 작업 화면에서 검토할 수 있다. 승인 권한은
요청 제출 권한과 독립적으로 부여할 수 있고 token은 browser에 노출되지 않는다. UI의 상태는
일시적인 projection이므로 새로고침이나 SSE 재연결 뒤에도 DB 상태와 다시 수렴한다. 다만 현재
서비스 계정은 로컬 사용자를 구분하지 않으므로 외부 공개 전에 사용자 인증과 감사 actor를
별도로 설계해야 한다.
