# ADR 0053: SCM 게시 실패를 공급자 중립 코드로 분류한다

## 배경

ORCH-055는 실패한 게시를 같은 원장 레코드에서 명시적으로 다시 시도할 수 있게 했다. 그러나
문자열 `failure_reason`만으로는 일시적인 API 장애와 작업공간 안전성 위반을 안정적으로 구분할
수 없다. 문자열 분석에 재시도 정책을 연결하면 공급자 메시지가 바뀔 때 잘못된 게시를 반복할
수 있고, Jarvis도 운영자에게 적절한 복구 방향을 설명하기 어렵다.

## 결정

- 실패 원장에는 사람이 읽는 `failure_reason`과 별도로 안정적인 `failure_code` 및
  `failure_retryable`을 저장한다.
- 공급자 중립 코드는 `workspace_state`, `provider_rejected`, `provider_unavailable`, `timeout`,
  `result_mismatch`, `unexpected`으로 제한한다.
- Publisher adapter는 `ScmPublisherFailure`로 코드와 재시도 가능 여부를 명시할 수 있다.
- Runtime 자체의 timeout은 재시도 가능으로, 작업공간 상태 및 결과 불일치는 재시도 불가로
  분류한다. 분류되지 않은 예외는 안전하게 `unexpected`, 재시도 불가로 기록한다.
- GitHub의 HTTP 408, 429 및 5xx와 전송 오류는 `provider_unavailable`로 분류한다. 그 밖의
  HTTP 거부는 `provider_rejected`로 기록한다.
- API, 프로젝트 이벤트와 Jarvis는 같은 분류 값을 사용한다. 이전 레코드는 두 필드가 null일
  수 있다.

## 결과

운영자는 실패 문자열을 해석하지 않고도 일시 장애인지 수동 확인이 필요한지 구분할 수 있다.
새 공급자는 같은 예외 계약만 구현하면 공급자별 오류 형식을 Control Plane 밖에 유지할 수 있다.

이 결정은 자동 재시도를 시작하지 않는다. 명시적 재시도 API는 기존처럼 운영자 판단으로 사용할
수 있으며, 향후 bounded backoff 정책은 `failure_retryable`, 시도 한도와 다음 실행 시각을 함께
정의하는 별도 변경으로 다룬다.
