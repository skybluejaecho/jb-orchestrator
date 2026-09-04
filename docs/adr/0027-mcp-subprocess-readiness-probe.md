# ADR 0027: MCP 운영 준비 상태를 별도 stdio 프로세스로 검사한다

## 상태

승인됨

## 배경

In-memory MCP E2E가 통과해도 실제 host에서 실행 명령, Python 환경, 자식 프로세스 환경
전달이나 stdio framing이 잘못될 수 있다. OpenClaw에 등록하기 전에 운영자가 이 경계를
독립적으로 확인할 방법이 필요하다. 응답하지 않는 child process가 진단 명령을 무기한
점유해서도 안 된다.

## 결정

- `jb mcp smoke --project-id ...` 명령을 제공한다.
- Probe는 현재 Python interpreter로 `jb_orchestrator.mcp_server.main`을 별도 process에서
  실행한다.
- 자식 process에는 현재 환경을 보존하면서 Control Plane URL과 API token을 명시적으로
  전달한다.
- 공식 MCP `ClientSession`으로 initialize, tool discovery, `get_project` 호출을 수행한다.
- 성공 결과에는 server identity, tool inventory와 조회된 project를 포함한다.
- 전체 handshake와 호출에는 15초 timeout을 적용하고, 실패 시 자식 process를 종료한다.
- Token 값은 결과나 오류에 포함하지 않는다.

## 결과

OpenClaw, Codex 또는 다른 host에 등록하기 전에 동일한 stdio process 경계를 검사할 수
있다. 이 probe의 성공은 jb-mcp 자체의 준비 상태를 의미하며, OpenClaw node plugin의 설치와
도구 허용 정책은 실제 OpenClaw 환경에서 별도로 검증해야 한다.
