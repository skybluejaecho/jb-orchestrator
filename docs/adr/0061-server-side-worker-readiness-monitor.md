# ADR 0061: Worker 배정 경보 평가는 서버 측 Monitor가 소유한다

## 배경

ORCH-063은 배정 불가 상태를 PostgreSQL 경보 원장으로 만들었지만 평가 호출은 Jarvis의 주기적
조회에 의존했다. 브라우저가 닫히면 새 경보와 복구 상태가 기록되지 않으므로, 이후 알림
어댑터가 이벤트를 구독하더라도 완전한 흐름을 보장할 수 없다.

## 결정

- `jb-readiness-monitor`는 독립 프로세스로 실행되며 설정된 주기마다 active 프로젝트를 평가한다.
- Monitor는 `readiness_monitor` Worker로 process heartbeat 원장에 등록한다.
- 한 cycle이 조회하는 프로젝트 수를 제한하고 archived 프로젝트는 평가하지 않는다.
- alert가 임계시간을 넘으면 `critical_at`을 한 번 기록하고 `worker.readiness_critical` 이벤트를
  한 번만 발행한다.
- 기존 명시적 evaluate API는 운영 및 호환성을 위해 유지하지만 Jarvis는 읽기 API만 호출한다.
- Monitor는 Worker를 자동 시작하거나 작업 claim 상태를 변경하지 않는다.

## 결과

경보의 생성, critical 전환과 복구가 GUI 수명과 분리된다. Jarvis, OpenClaw와 이후 알림
어댑터는 PostgreSQL 원장과 프로젝트 이벤트를 동일한 기준으로 소비할 수 있다. 자동 복구와
외부 알림 전달은 별도 정책 및 어댑터로 남는다.
