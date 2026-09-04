# ADR 0023: 요청 출처를 실행 런타임과 분리한다

## 상태

승인됨

## 배경

초기 REST API는 Jarvis 같은 클라이언트가 요청을 등록하기에는 충분하지만 요청이 어느
시스템, 사용자, 대화에서 시작되었는지 보존하지 않았다. OpenClaw, CLI, Webhook 또는
스케줄러를 추가하면 서로 다른 입력 채널이 같은 멱등성 key를 사용할 수도 있다.

Jarvis나 OpenClaw를 핵심 도메인에 직접 결합하면 새로운 입력 방식을 추가할 때 Workflow
엔진과 저장 모델까지 변경해야 한다. 요청 출처와 실제 작업 Executor도 독립적으로 선택할
수 있어야 한다.

## 결정

- 모든 입력 어댑터는 `DispatchProjectRequest` application command를 만든다.
- command는 Project, 사용자 prompt, 멱등성 key와 불변 `RequestOrigin`을 포함한다.
- `RequestOrigin`은 다음의 transport-neutral 식별자만 저장한다.
  - `ingress_key`
  - `external_request_id`
  - 선택적인 `actor_id`
  - 선택적인 `conversation_id`
- `ingress_key`는 DB enum이 아니라 규칙을 검증한 문자열이다. 새로운 입력 어댑터 추가에
  migration이 필요하지 않게 한다.
- Dispatch 멱등성 namespace를 `(project_id, ingress_key, idempotency_key)`로 확장한다.
- 동일 namespace에서 prompt, title, origin 또는 요청별 Workflow 선택이 달라지면
  `409 Conflict`로 거부한다.
- 생성된 User Request와 `request.created` 이벤트에 origin을 보존한다.
- 기존 origin 없는 User Request는 읽을 수 있도록 nullable 상태로 유지한다.
- REST adapter는 `X-JB-Ingress-Key`, `X-JB-External-Request-ID`, `X-JB-Actor-ID`,
  `X-JB-Conversation-ID` 헤더를 command로 변환한다. 생략 시 ingress는 `rest`, 외부 요청
  ID는 `Idempotency-Key`를 사용한다.
- 인증 token, Gateway secret, 회신 자격 증명은 origin에 저장하지 않는다.

## 보안 경계

현재 origin 헤더는 호출자가 주장한 provenance이며 인증된 신원은 아니다. 원격 입력을
허용하기 전에 후속 인증·권한 단계에서 service account와 project scope를 검증하고,
검증된 actor 정보를 서버가 결정해야 한다.

OpenClaw에서는 사용자 요청을 받는 Control Agent와 Workflow task를 수행하는 Worker
Agent를 분리한다. Worker Agent에는 새로운 Dispatch 권한을 주지 않는다.

## 결과

Jarvis, OpenClaw, CLI와 이후 입력 어댑터가 같은 application service를 사용하며, 요청
입구와 `executor_key`를 자유롭게 조합할 수 있다. 서로 다른 ingress는 같은 외부 key를
안전하게 사용할 수 있고 동일 ingress의 재전송은 원래 실행으로 수렴한다.
