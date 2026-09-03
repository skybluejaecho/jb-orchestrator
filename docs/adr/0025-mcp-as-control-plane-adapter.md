# ADR 0025: MCP 서버를 Control Plane API 어댑터로 둔다

## 상태

승인됨

## 배경

OpenClaw, Codex 및 다른 MCP 호스트가 jb-orchestrator를 도구로 사용하려면 MCP interface가
필요하다. 그러나 MCP 서버가 DB와 application service를 별도로 호출하면 REST API와 권한,
멱등성, 오류 계약이 달라질 수 있다. 또한 MCP 서버 자체를 외부 네트워크에 공개하면 별도의
인증 및 운영 경계가 하나 더 생긴다.

## 결정

- MCP는 새로운 오케스트레이터가 아니라 기존 Control Plane REST API의 입력 어댑터다.
- 첫 버전은 로컬 프로세스로 실행하는 stdio transport만 제공한다.
- MCP 서버는 `JB_CONTROL_PLANE_URL`과 `JB_API_TOKEN`으로 API를 호출한다.
- MCP tool은 DB에 직접 접근하지 않으며 권한 판정은 API service account가 수행한다.
- 요청 dispatch의 ingress는 서버가 `mcp`로 고정하고 호출자가 제공한 idempotency key를
  그대로 전달한다.
- 조회, dispatch, 승인, 취소 도구를 분리하고 MCP `ToolAnnotations`에 읽기 전용,
  멱등성, 파괴적 작업 여부를 표시한다.
- Annotation은 모델을 위한 힌트일 뿐 보안 경계로 신뢰하지 않는다.
- 오류에는 HTTP 상태와 안전한 problem detail만 포함하고 token은 노출하지 않는다.

## 결과

MCP를 지원하는 어떤 호스트든 동일한 stdio 서버를 등록할 수 있으며 Jarvis나 OpenClaw에
종속되지 않는다. 호스트가 MCP를 직접 지원하지 않으면 같은 REST API를 호출하는 adapter를
사용할 수 있다. Streamable HTTP transport는 실제 원격 배포와 별도 인증 필요성이 확인된
뒤 추가한다.
