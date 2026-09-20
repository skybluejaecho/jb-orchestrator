# ADR 0026: MCP 연결을 실제 protocol 경계에서 검증한다

## 상태

승인됨

## 배경

FastMCP 내부 함수를 직접 호출하는 단위 테스트만으로는 MCP client 초기화, tool discovery,
argument serialization, structured result 반환이 실제 호스트에서도 작동한다고 보장할 수
없다. 또한 OpenClaw의 Gateway protocol이 MCP server와 tool 호출을 표현하더라도 배포마다
stdio server를 적재하는 node plugin 구성이 다를 수 있다.

## 결정

- 공식 SDK의 in-memory transport로 실제 `ClientSession`과 FastMCP server를 연결한다.
- E2E 검증은 tool discovery부터 시작하여 다음 전체 경로를 통과해야 한다.

```text
MCP ClientSession
  -> FastMCP tool
  -> ControlPlaneClient
  -> API bearer 인증/프로젝트 권한
  -> DispatchProjectRequest
  -> Workflow snapshot + PostgreSQL 계약
```

- 같은 idempotency key로 재호출하여 최초 Workflow로 수렴하는지 확인한다.
- `jb mcp config`는 범용 stdio 설정을 출력하되 실제 token을 출력하지 않는다.
- `jb mcp check`는 token, API 연결, project scope를 한 번에 진단한다.
- OpenClaw Control Agent와 Worker Agent를 분리한다. Control Agent만 MCP dispatch 권한을
  가지며 Worker는 할당된 Workflow task만 실행한다.
- 특정 OpenClaw 배포의 node plugin 설치 형식을 core MCP 서버에 내장하지 않는다.

## 결과

MCP 호스트 종속 설정과 jb-orchestrator의 protocol 계약이 분리된다. OpenClaw에서 실제
node-hosted MCP plugin을 설치할 수 있는 환경이 준비되면 생성된 stdio descriptor를 해당
plugin 형식으로 변환하는 얇은 adapter만 추가하면 된다.
