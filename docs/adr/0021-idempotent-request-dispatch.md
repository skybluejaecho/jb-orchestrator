# ADR 0021: 프로젝트 범위의 멱등성 영수증으로 요청 디스패치를 보호한다

## 상태

승인됨

## 배경

Jarvis, OpenClaw 또는 다른 클라이언트는 응답을 받지 못하면 요청을 재전송한다. 단순한
POST 요청은 재전송마다 새로운 User Request, Run, Workflow Execution을 만들 수 있다.
사후 중복 조회만으로는 동시에 도착한 두 요청이 모두 “아직 없음”을 확인하는 경쟁 조건을
막을 수 없다.

멱등성 판단은 에이전트 세션이나 클라이언트 메모리가 아니라 PostgreSQL에 남아야 한다.
또한 같은 key로 다른 사용자 의도를 보내는 실수는 조용히 기존 결과를 반환하지 않아야 한다.

## 결정

- `POST /v1/projects/{project_id}/dispatches`에 `Idempotency-Key` 헤더를 필수로 요구한다.
- key는 trim 후 1~128자이며 프로젝트 안에서만 고유하다.
- prompt와 title을 정규화하고 canonical JSON의 SHA-256 digest를 저장한다.
- 별도 `request_dispatch_receipts` row가 key, payload digest, Request ID, Run ID,
  Workflow Execution ID를 기록한다.
- 최초 요청은 `INSERT ... ON CONFLICT DO NOTHING RETURNING`으로 영수증 소유권을
  원자적으로 획득한다.
- 영수증 claim, 세 aggregate 생성, Workflow 시작, 영수증 완료를 하나의 트랜잭션에서
  커밋한다.
- 생성 중 실패하면 영수증 claim도 롤백되므로 같은 key로 안전하게 다시 시도할 수 있다.
- 이미 완료된 동일 key·동일 payload 요청은 원래 aggregate를 반환하고 `replayed=true`로
  표시한다. 새로운 이벤트도 만들지 않는다.
- 동일 key·다른 payload 요청은 `409 Conflict`로 거부한다.
- 완료되지 않은 영수증이 관찰되면 중복 실행을 시작하지 않고 진행 중 충돌로 처리한다.
- DB check constraint로 결과 ID 세 개와 완료 시각이 모두 있거나 모두 없도록 강제한다.

## 경쟁 요청 흐름

```text
Client A ─┐
          ├─ same project + key ─> PostgreSQL unique claim
Client B ─┘                            │
                         ┌─────────────┴─────────────┐
                         │                           │
                    A: claim 성공              B: conflict 대기
                         │                           │
              Request + Run + Workflow              │
                         │                           │
                    receipt 완료 ─────────────> 원래 결과 replay
```

## 결과

네트워크 타임아웃과 클라이언트 재시도가 중복 에이전트 실행이나 중복 비용을 만들지 않는다.
바인딩이 나중에 변경되더라도 같은 key의 재전송은 최초 Workflow 스냅샷을 반환한다.

후속 단계에서는 보존 기간과 삭제 정책, 사용자별 key namespace, 통합 조회 화면에서의
멱등성 영수증 감사 정보를 다룬다.
