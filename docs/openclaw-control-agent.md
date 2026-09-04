# OpenClaw Control Agent 연결 지침

## 역할 분리

OpenClaw를 한 종류의 만능 agent로 연결하지 않는다.

- **Control Agent**: 사용자 대화를 받고 `jb-mcp` 도구로 요청을 등록하고 상태를 설명한다.
- **Worker Agent**: jb-orchestrator Worker가 할당한 특정 Workflow node만 실행한다.
- **jb-orchestrator**: 프로젝트, Workflow, 승인, 멱등성, 예산과 실행 상태의 원장이다.
- **OpenClaw Gateway**: agent session과 대화 context를 유지한다.

Control Agent token에는 대상 프로젝트의 `project.read`, `request.dispatch`를 부여한다.
승인이나 취소까지 맡길 때만 `workflow.approve`, `run.cancel`을 추가한다. Worker Agent에는
새 사용자 요청을 만드는 `request.dispatch` 권한을 주지 않는다.

## 연결 준비

```powershell
uv run alembic upgrade head
uv run jb auth issue `
  --key openclaw-control `
  --name "OpenClaw Control Agent" `
  --permission project.read `
  --permission request.dispatch `
  --project-id <project-uuid>

$env:JB_CONTROL_PLANE_URL="http://127.0.0.1:8000"
$env:JB_API_TOKEN="<issued-token>"

uv run jb mcp check --project-id <project-uuid>
uv run jb mcp config --project-path <repository-path>
uv run jb mcp smoke --project-id <project-uuid>
```

`check`는 API 인증과 scope를, `smoke`는 실제 별도 stdio process와 MCP handshake까지
검사한다. 두 검사가 모두 성공한 뒤 `config`가 출력한 JSON을 MCP host 또는 OpenClaw
node-hosted plugin이 요구하는 설정 형식에 맞춰 등록한다. 현재 저장소에 고정된 OpenClaw
Gateway protocol은 MCP server/tool 계약을 포함하지만, Gateway client 패키지만으로 plugin
설치까지 수행하지는 않는다. 실제 OpenClaw 배포의 plugin loader 설정은 해당 배포에서
확인해야 한다.

## Control Agent 지시문 예시

```text
너는 사용자의 요청을 직접 구현하는 Worker가 아니라 jb-orchestrator Control Agent다.
대상 프로젝트 UUID는 <project-uuid>다.

새 요청을 받으면:
1. 요청이 충분히 구체적인지 확인한다.
2. 채널의 원본 message/event ID를 기반으로 안정적인 idempotency_key를 만든다.
3. dispatch_request를 한 번 호출한다.
4. 네트워크 오류로 재시도할 때는 반드시 같은 key와 같은 payload를 사용한다.
5. 반환된 request, run, workflow ID를 사용자에게 알려준다.
6. 이후 조회 도구로 DB에 기록된 상태를 설명한다.

승인과 취소는 사용자가 명시적으로 요청한 경우에만 실행한다.
Workflow나 프로젝트 상태를 OpenClaw 자체 메모리만으로 추측하지 않는다.
```

`external_request_id`에는 원본 채널 message ID, `actor_id`에는 사용자 ID,
`conversation_id`에는 OpenClaw session 또는 채널 대화 ID를 전달한다. 민감한 token이나
Gateway 자격 증명은 이 필드에 저장하지 않는다.
