# ADR 0056: SCM 게시의 각 Worker 시도를 별도 원장으로 보존한다

## 배경

게시 원장의 `attempt_count`와 현재 실패 정보만으로는 어느 Worker가 각 시도를 수행했는지,
재시도가 수동·자동·임대 만료 회수 중 무엇이었는지, 이전 실패가 어떻게 복구됐는지 조회할 수
없다. 이벤트만 재구성하면 감사와 화면 조회가 이벤트 스키마에 과도하게 결합된다.

## 결정

- Worker가 게시를 claim할 때 publication 변경과 같은 트랜잭션으로 attempt 레코드를 만든다.
- attempt는 publication별 연속 번호, 시작 계기, Worker, 내부 임대 토큰, 시작·종료 시각을 가진다.
- 시작 계기는 `initial`, `manual`, `automatic`, `lease_recovery`로 구분한다.
- 성공 결과 또는 실패 이유·분류·재시도 가능 여부를 해당 attempt에 확정하고 이전 레코드는
  수정하지 않는다.
- 배포 전 이미 claim된 publication은 완료 시 `lease_recovery` attempt를 보완하여 결과 유실을
  막는다.
- `GET /v1/scm-publications/{id}/attempts`는 최신 시도부터 반환하되 내부 임대 토큰은 노출하지
  않는다.
- Jarvis는 게시별로 사용자가 펼칠 때 원장을 조회하고 타임라인으로 표시한다.

## 결과

현재 publication은 빠른 작업 제어용 상태로 유지되고 attempt 원장은 감사·진단용 사실 기록이
된다. 재시도 정책이 추가되더라도 이전 실패와 실행 주체를 덮어쓰지 않으며, PostgreSQL 한 곳이
Worker와 Jarvis가 공유하는 정합성 기준이 된다.
