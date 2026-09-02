# ADR 0008: 버전형 모델 카탈로그와 결정적 모델 라우팅

- 상태: 채택
- 날짜: 2026-09-02

## 배경

모든 작업에 가장 강한 모델을 사용하면 비용과 지연이 불필요하게 증가한다. 반대로
저렴한 모델을 우선하는 단순 정책은 고위험 작업의 품질을 떨어뜨릴 수 있다. 모델 선택을
executor 또는 LLM의 자유 판단에만 맡기면 동일 workflow를 재시도할 때 결과가 바뀌고,
어떤 정책으로 모델이 선택됐는지 감사하기 어렵다.

## 결정

모델의 실행 정보와 비용·능력 정보를 immutable `ModelProfile` 버전으로 등록한다.

- provider와 실제 `model_id`
- economy, balanced, advanced tier
- context window와 백만 token당 input/output 비용
- coding, vision 같은 capability
- 사용할 수 있는 executor key
- 운영 중 선택을 막을 수 있는 enabled 상태

Task node는 선택할 모델명을 직접 쓰는 대신 다음 routing 요구사항을 선택적으로 선언한다.

- complexity, risk, quality
- 필수 capability
- 예상 input token과 최대 output token
- 최대 허용 비용

정책은 complexity, risk, quality 중 가장 높은 요구 수준을 최소 tier로 사용한다. 그 후
enabled, executor, capability, context window, 최대 비용을 모두 충족하는 profile만 남기고,
충족 가능한 가장 낮은 tier에서 예상 비용이 가장 낮은 profile을 선택한다. 완전한 동률은
profile key와 최신 version 순으로 결정한다.

조건을 만족하는 profile이 없으면 더 낮은 tier를 선택하거나 예산을 초과하지 않고
workflow 시작을 실패시킨다. 선택 결과에는 profile 전체, 정책 버전, 요구 tier, 예상 비용,
선택 근거를 담아 workflow snapshot에 저장한다. Worker의 `TaskClaim`은 이 고정된 결과를
executor에 전달한다.

## 결과

- 같은 snapshot의 재시도와 worker 인계는 같은 모델 선택을 사용한다.
- 가격이나 모델 속성 변경은 기존 profile을 수정하지 않고 새 version을 등록한다.
- executor는 routing 정책을 재구현하지 않고 provider와 model ID를 소비한다.
- 실제 token 사용량 집계, 프로젝트 전체 budget reservation, 동적 LLM judge는 후속 단계로
  남는다. LLM judge를 추가하더라도 결정적 정책의 허용 범위 안에서만 동작해야 한다.
