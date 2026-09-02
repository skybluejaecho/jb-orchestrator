# ADR 0009: 프로젝트 예산 예약과 append-only 사용량 원장

- 상태: 채택
- 날짜: 2026-09-02

## 배경

모델 라우터가 저렴한 모델을 선택하더라도 여러 worker가 동시에 실행되면 프로젝트의
남은 예산을 각각 사용할 수 있다고 판단해 전체 한도를 초과할 수 있다. Executor 호출은
DB transaction 밖에서 실행되며 worker crash와 retry가 가능하므로, 단순한 누적 비용
컬럼만으로는 중복 차감과 유실을 막을 수 없다.

## 결정

프로젝트별 USD `BudgetAccount`와 task visit별 `BudgetReservation`, append-only
`UsageRecord`를 둔다. 예산 설정이 없는 프로젝트는 기존 실행과의 호환성을 위해 제한
없이 동작한다.

모델 선택이 있는 task의 실행 순서는 다음과 같다.

1. Worker가 executor를 호출하기 직전에 snapshot에 고정된 예상 최대 비용을 예약한다.
2. PostgreSQL에서 프로젝트 budget account row를 `FOR UPDATE`로 잠가 동시 예약을
   직렬화한다.
3. Workflow task의 안정적인 idempotency key를 reservation unique key로 사용한다.
4. Executor가 성공 또는 명시적 failure 결과와 실제 input/output token을 반환하면,
   snapshot에 고정된 단가로 실제 비용을 계산해 예약을 정산한다.
5. Worker crash나 재시도 가능한 오류에서는 예약을 유지한다. 다음 attempt는 같은
   reservation을 재사용한다.
6. 최종 실패인데 실제 사용량을 확인할 수 없으면 예약액 전체를 보수적으로
   `estimated_forfeit` 비용으로 기록한다.
7. Run 또는 workflow가 취소되면 아직 실행되지 않은 active reservation을 해제한다.

실제 사용량이 예상치를 초과했다면 이미 발생한 비용을 숨기지 않고 spent가 limit을
초과하도록 기록한다. 이후 신규 예약은 차단된다. Usage record는 reservation당 하나만
생성되며 수정하지 않는다.

## 결과

- 동시 worker가 같은 프로젝트의 남은 예산을 이중으로 예약하지 않는다.
- 같은 logical task의 retry는 예약과 정산을 중복 생성하지 않는다.
- 실제 token 사용량, 보수적 미확인 비용, 현재 reserved/spent/available 금액을 구분할
  수 있다.
- 현재는 USD 프로젝트 lifetime budget을 사용한다. 기간별 reset, 조직/사용자 계층 예산,
  provider invoice reconciliation과 cached-token 별도 단가는 후속 범위로 남는다.
