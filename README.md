# jb-orchestrator

`jb-orchestrator` is a local-first orchestration core for reproducible agent workflows.
It stores execution state in PostgreSQL and exposes the same application behavior through
API, worker, CLI, and later MCP adapters.

## Implemented foundations

ORCH-001 established the repository foundation:

- FastAPI application with health endpoints
- worker and administration CLI entry points
- PostgreSQL development service
- lint, type-check, test, and GitHub Actions CI configuration
- modular-monolith package boundaries

ORCH-002 adds the initial durable domain:

- Project, UserRequest, and Run domain entities
- guarded request and run lifecycle transitions
- SQLAlchemy persistence records and repository ports
- Alembic initial PostgreSQL migration
- optimistic concurrency versioning for runs

ORCH-003 exposes the first control-plane use cases:

- transactional SQLAlchemy repositories and Unit of Work
- project registration and request/run REST endpoints
- run approval and cancellation controls
- administration CLI commands backed by the REST API
- durable application events for request and run state changes

ORCH-004 adds the deterministic workflow core:

- validated, versioned workflow graph definitions
- immutable per-run snapshots and durable node execution state
- explicit task, approval, terminal, retry, and bounded repair-loop transitions
- transactional workflow services and append-only transition events
- PostgreSQL migrations and in-memory/SQLAlchemy round-trip tests

ORCH-005 adds the distributed worker runtime:

- atomic READY-node claiming with PostgreSQL `FOR UPDATE SKIP LOCKED`
- expiring worker leases, token validation, heartbeat renewal, and crash recovery
- stable per-node-visit idempotency keys for at-least-once execution
- executor ports for later Codex, Orca, OpenClaw, MCP, or local adapters
- one-shot and continuous polling runtime with timeout and retry handling

ORCH-006 adds installable executor routing:

- immutable task `executor_key`, instructions, and JSON configuration
- worker capability filtering before PostgreSQL task claim
- runtime executor registry with duplicate and contract validation
- adapter discovery through the `jb_orchestrator.executors` Python entry-point group
- worker CLI startup checks and installed-executor listing

ORCH-007 adds the versioned skill catalog:

- immutable local, Git, and archive skill metadata with SHA-256 content identity
- REST registration, latest-version listing, and exact-version lookup
- multiple exact skill references per workflow task node
- resolved skill metadata copied into each workflow execution snapshot and task claim
- explicit separation between skills, executor adapters, and MCP tool servers

ORCH-008 adds verified skill materialization:

- safe local, pinned Git, and size-limited archive source fetchers
- canonical directory SHA-256 verification before executor invocation
- atomic content-addressed cache with verification on every reuse
- configured remote-host allowlists and path, symlink, and archive traversal defenses
- verified skill entrypoint paths delivered through each task claim

ORCH-009 adds deterministic model routing:

- immutable, versioned model profiles with provider, tier, context, price, and capabilities
- explicit complexity, risk, quality, context, capability, and maximum-cost requirements
- fail-closed filtering followed by deterministic cheapest-sufficient model selection
- routing policy version, reasons, and estimated cost pinned in workflow snapshots
- selected provider and model identity delivered to executor task claims

ORCH-010 adds project budget enforcement:

- project-level USD limits with separate reserved, spent, and available balances
- row-locked, idempotent maximum-cost reservations before executor invocation
- append-only actual token usage and conservative unknown-usage forfeiture records
- retry-safe settlement using stable workflow task idempotency keys
- active reservation release when a run or workflow is cancelled

ORCH-011 exposes the workflow control plane:

- versioned workflow definition registration, latest-version listing, and exact lookup
- workflow execution startup for an existing run with an immutable definition snapshot
- workflow and node execution status queries by run or execution identifier
- explicit approval resolution and workflow cancellation endpoints
- domain validation errors returned as structured HTTP problem details

ORCH-012 hardens long-running worker execution:

- periodic PostgreSQL lease renewal while an executor is active
- fail-closed cancellation when heartbeat ownership can no longer be renewed
- bounded timeout and graceful worker-stop cleanup
- optional idempotent provider-side cancellation hooks for remote agent runtimes
- configurable heartbeat and cancellation timeout settings

ORCH-013 validates the OpenClaw Gateway boundary before production integration:

- exact-pinned official Gateway client and protocol packages in an isolated Node.js spike
- protocol-validated `agent` and `agent.wait` execution using stable JB idempotency keys
- exact-run cancellation through `sessions.abort` and same-session continuation semantics
- documented PostgreSQL-to-OpenClaw ownership boundary and production adapter follow-up

See `tools/openclaw-gateway-spike/README.md` for the executable contract test and live Gateway
instructions. Live validation requires an independently configured OpenClaw Gateway and is not a
prerequisite for the Python application runtime.

ORCH-014 adds the first installable OpenClaw executor adapter:

- PostgreSQL ledger mapping stable JB task keys to OpenClaw sessions and runs
- crash-safe resume without duplicate `agent` calls and persisted terminal projections
- bounded JSON subprocess bridge that keeps credentials and prompts out of process arguments
- exact-run provider cancellation integrated with the ORCH-012 worker lifecycle
- separately installed `openclaw` executor entry point, leaving the core runtime optional

See `adapters/openclaw/README.md` for installation and current production-hardening requirements.

ORCH-015 hardens OpenClaw Gateway authentication:

- persistent Ed25519 worker identity with challenge-bound signatures
- shared credentials used only for initial device pairing bootstrap
- role-scoped Gateway device-token persistence, rotation, and clearing
- atomic private state writes outside PostgreSQL and process arguments
- optional TLS certificate fingerprint pinning for remote `wss://` Gateways

ORCH-016 exposes durable external execution observation:

- PostgreSQL-backed external execution detail and filtered list APIs
- idempotent prepared, accepted, and terminal external execution events
- polling-friendly status projections for Jarvis and other clients

ORCH-017 adds a resumable external execution event stream:

- database-issued monotonic event sequences for deterministic replay order
- SSE delivery with durable event IDs, idle heartbeats, and proxy buffering disabled
- reconnection through the standard `Last-Event-ID` header or an initial `after` cursor
- ledger replay before live polling so temporary client disconnects do not lose events

ORCH-018 adds durable task context and artifacts:

- original request and repository identity pinned in each workflow snapshot
- immutable JSON artifacts stored for every completed task node visit
- only the latest artifacts from direct predecessor nodes delivered in each task claim
- structured request, project, artifact, and verified-skill context rendered for OpenClaw
- workflow artifact history exposed through the control-plane API

ORCH-019 adds composable, versioned phase packs:

- reusable phase roles, instructions, skill references, and JSON output contracts
- named required or optional phase inputs independent of a workflow graph
- explicit workflow-node mappings from input names to producer-node artifacts
- exact phase-pack versions pinned into each workflow execution snapshot
- named inputs and output contracts rendered for OpenClaw execution
- legacy nodes retaining automatic direct-predecessor artifact delivery

ORCH-020 enforces phase output contracts:

- phase output contracts validated as JSON Schema Draft 2020-12
- malformed schemas rejected before a phase-pack version is registered
- invalid successful outputs converted into structured failure artifacts
- original rejected output and deterministic validation details retained for repair
- contract failures routed through ordinary workflow failure edges and repair loops
- valid successes and explicit executor failures preserved without rewriting

ORCH-021 adds deterministic parallel workflow regions:

- explicit non-executing fork and all-source join control nodes
- multiple branch tasks becoming READY for concurrent workers
- join activation only after every direct predecessor has completed
- workflow-aggregate row locking around short claim and transition transactions
- sibling task cancellation when a parallel path terminates or fails the workflow
- named Phase Pack inputs combining durable artifacts from independent branches

ORCH-022 adds project-level workflow selection and one-call request dispatch:

- one exact workflow definition version bound to each project
- atomic User Request, Run, Workflow Execution, and event creation
- selected definition and request context pinned into the execution snapshot
- binding changes affecting only future dispatches
- explicit manual workflow startup retained for administrative use

ORCH-023 synchronizes the complete execution lifecycle:

- workflow status projected transactionally to its parent Run
- successful workflows completing their User Request
- failed Runs retaining an active Request for a later retry attempt
- cancellation from either Run or Workflow closing the complete active hierarchy
- phase-neutral Run states for freely composed workflows
- row locks and durable lifecycle events protecting concurrent state changes

ORCH-024 makes one-call request dispatch retry-safe:

- required project-scoped `Idempotency-Key` headers on dispatch requests
- atomic PostgreSQL claims allowing only one creator for concurrent duplicate submissions
- durable receipts mapping client keys to the original Request, Run, and Workflow Execution
- normalized payload digests rejecting reuse of a key for different user intent
- completed retries returning the original aggregates without creating execution state

ORCH-025 adds project-scoped observation for local GUIs and other clients:

- filterable Project, User Request, Run, and Workflow Execution list APIs
- project membership derived from existing durable database relationships
- one resumable SSE stream covering project, request, run, workflow, external execution, and budget events
- catalog-global events excluded from project streams
- common aggregate identity included in SSE payloads while preserving external-stream compatibility

ORCH-026 separates request ingress from execution runtimes:

- transport-neutral request origin persisted with each dispatched User Request
- one application command shared by REST and future MCP, CLI, webhook, or scheduler adapters
- extensible string ingress keys avoiding catalog migrations for new client types
- project-and-ingress-scoped idempotency preventing unrelated clients from colliding
- external request, actor, and conversation identifiers returned through observation APIs

ORCH-027 protects remote control-plane access:

- hashed bearer credentials issued to named service accounts
- explicit read, dispatch, approval, cancellation, and administration permissions
- project-scoped authorization for Jarvis, OpenClaw, CLI, and future ingress adapters
- public health probes with authenticated `/v1` APIs
- fail-closed startup when an unauthenticated API is bound outside loopback

ORCH-028 exposes a host-neutral MCP adapter:

- official MCP Python SDK with a local stdio transport
- authenticated delegation to the existing Control Plane API instead of direct DB access
- bounded tools for project observation, idempotent dispatch, approval, and cancellation
- MCP safety annotations backed by API-enforced service-account permissions
- stable `mcp` request origin shared by Codex, OpenClaw, and other MCP hosts

ORCH-029 verifies and operationalizes the MCP connection:

- real MCP `ClientSession` initialization, discovery, and structured tool calls
- end-to-end dispatch through API authentication into a durable Workflow snapshot
- protocol-level idempotent replay verification
- secret-safe stdio host configuration generation
- one-command API token and project-scope diagnostics
- concrete OpenClaw Control Agent role and instruction template

ORCH-030 validates the deployable stdio process boundary:

- real child-process launch of the installed jb-mcp module
- MCP initialization and tool inventory over operating-system stdio pipes
- authenticated project lookup through a live local HTTP socket
- bounded readiness timeout with child-process cleanup
- one `jb mcp smoke` command to run before host registration

ORCH-031 starts Jarvis as a local observation dashboard:

- responsive project, request, and workflow control-room view
- server-side bearer proxy keeping service-account tokens out of the browser
- project SSE reconnection with snapshot refresh after durable events
- explicit loading, empty, disconnected, and live states
- read-only first increment independent from OpenClaw or any executor runtime

ORCH-032 adds a bounded Jarvis request-ingress flow:

- project-aware request composer using the existing default workflow binding
- server-side dispatch proxy with a fixed `jarvis` ingress identity
- retry-stable idempotency keys preventing duplicate execution after response loss
- scoped `request.dispatch` permission without approval or cancellation authority
- immediate snapshot refresh while SSE remains the durable update path

ORCH-033 makes Jarvis changes independently verifiable:

- Node-based CI job for deterministic install, format, lint, test, and production build
- server proxy tests proving bearer-token isolation and fail-closed configuration
- dispatch contract tests covering headers, payload normalization, and upstream errors
- retry tests proving stable idempotency keys for unchanged inputs
- local and CI commands backed by the same committed npm lockfile

ORCH-034 adds explicit workflow review to Jarvis:

- on-demand execution detail and immutable task-artifact inspection
- approval and rejection controls shown only for nodes awaiting a decision
- a deliberate two-step confirmation before the workflow graph is advanced
- server-side `workflow.approve` authorization without exposing bearer tokens
- SSE-triggered detail refresh while the Control Plane remains the source of truth

ORCH-035 adds guarded execution cancellation to Jarvis:

- cancellation available only from a selected non-terminal execution
- exact execution-specific confirmation text before the destructive request is enabled
- server-side `run.cancel` authorization without exposing bearer tokens
- Control Plane conflict propagation for terminal-state and concurrent-update races
- detail and overview reconciliation after cancellation and subsequent SSE events

ORCH-036 adds a process-level local system smoke test:

- real PostgreSQL migrations, authenticated Control Plane, Worker, and Jarvis processes
- deterministic test-only executor installed only for the smoke command
- end-to-end request dispatch, task artifact, approval, completion, and cancellation checks
- bounded readiness and transition timeouts with child-process cleanup
- a dedicated CI job that exercises the complete local deployment boundary

ORCH-037 adds declarative orchestration bundles:

- one versioned YAML document for Project, Skill, Model, Phase Pack, Workflow, and Binding inputs
- offline schema, output-contract, graph, and bundled phase-input validation
- read-only planning with explicit create, update, unchanged, and immutable-conflict actions
- external exact-version dependency checks against the Control Plane
- conflict-free ordered application through existing authenticated APIs
- retry-safe convergence without storing credentials in the bundle

ORCH-038 adds a composable starter kit:

- one non-overwriting `jb bundle init` command backed by packaged template assets
- independently versioned planning, implementation, verification, repair, and synthesis phases
- verified local `SKILL.md` packages including examples that combine multiple skills
- planning-only, bounded repair-loop, and parallel fork/join workflow compositions
- structured OpenClaw terminal output promoted to contract-validated phase artifacts
- original provider terminal results retained in the external execution ledger

ORCH-039 adds deterministic artifact-conditional routing:

- task edges may match a contract-validated artifact value through an RFC 6901 JSON Pointer
- conditional edges for one outcome share a path and use distinct scalar values
- an optional unconditional edge provides an explicit default route
- absent matches without a default fail the workflow instead of guessing a destination
- conditions remain pinned in workflow snapshots and round-trip through REST and bundles
- the starter delivery workflow routes `approve` to human review and `changes_requested` to repair

ORCH-040 adds request-scoped workflow selection:

- a project-scoped option endpoint returns the current default and selectable exact versions
- dispatch may pin one exact workflow for that request without changing the project binding
- omitted selection continues to use the project default with backward-compatible behavior
- workflow selection participates in the idempotency fingerprint and durable request event
- MCP exposes option discovery and exact selection to OpenClaw or other control agents
- Jarvis offers the same default-or-exact selection in its request composer

ORCH-041 adds workflow composition previews:

- workflow options include the exact graph nodes and edges used by each selectable version
- referenced phase packs are resolved with their names, descriptions, and skill references
- direct and phase-pack-provided skills are deduplicated into one effective skill summary
- MCP control agents can explain a composition before asking the user to choose it
- Jarvis shows the selected workflow's stages, phase packs, and skill sources before dispatch
- previews remain read-only and execution still uses the immutable workflow snapshot

ORCH-042 adds request-scoped Skill composition:

- workflow options expose safe summaries for the latest registered Skills
- one request may add exact Skill versions to selected task nodes
- add-ons never remove the Workflow or Phase Pack's required Skills
- node and Skill references are validated before an execution is created
- normalized Skill add-ons participate in the dispatch idempotency fingerprint and request event
- the augmented node definitions and resolved Skills are pinned in the immutable execution snapshot
- MCP and Jarvis share the same task-node Skill add-on contract

ORCH-043 adds an explicit OpenClaw deployment acceptance boundary:

- pinned official Gateway protocol and bridge contract tests run as an independent CI job
- local diagnostics validate Node.js, bridge, credential/device state, and remote TLS pinning
- operator-invoked live checks prove idempotent replay and same-session continuation
- exact-run cancellation is available as a separate, usage-incurring opt-in probe
- diagnostic reports omit prompts, session contents, and credentials

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker with Docker Compose

## Setup

```powershell
Copy-Item .env.example .env
uv sync --extra dev
docker compose up -d postgres
uv run alembic upgrade head
```

원격 클라이언트를 연결하려면 먼저 서비스 계정을 발급합니다. Token 원문은 이 명령에서만
표시되므로 즉시 안전한 secret 저장소에 보관해야 합니다.

```powershell
uv run jb auth issue `
  --key openclaw-control `
  --name "OpenClaw Control Agent" `
  --permission project.read `
  --permission request.dispatch `
  --project-id <project-uuid>
```

서버에는 `JB_API_AUTH_ENABLED=true`를 설정합니다. CLI client에는 별도로
`JB_API_TOKEN=<발급된-token>`을 설정합니다. `JB_API_AUTH_ENABLED=false`인 서버는
`127.0.0.1`, `localhost`, `::1` 외 주소에 바인딩되지 않습니다. 계정을 폐기하려면
`uv run jb auth revoke <account-uuid>`를 실행합니다.

## Run

```powershell
uv run jb-api
uv run jb doctor
uv run jb skill digest skills/my-skill
uv run jb-worker --list-executors
uv run jb-mcp
# After installing at least one executor adapter:
uv run jb-worker --once
```

Jarvis 로컬 대시보드는 별도 터미널에서 실행합니다. 전용 서비스 계정에는 상태 조회와 요청
제출 외에 승인 기능을 사용할 경우 `workflow.approve`, 취소 기능을 사용할 경우 `run.cancel`
권한도 부여합니다. 사용자 인증 계층을 추가하기 전까지 외부 네트워크에 공개하거나 배포하지
않습니다.

```powershell
Copy-Item apps/jarvis/.env.example apps/jarvis/.env.local
Set-Location apps/jarvis
npm install
npm run dev
```

### MCP host registration

`jb-mcp`는 독립적인 오케스트레이터나 DB 서버가 아니라 인증된 Control Plane API
클라이언트입니다. MCP host가 실행하는 프로세스 환경에 `JB_CONTROL_PLANE_URL`과
`JB_API_TOKEN`을 전달합니다.

```json
{
  "mcpServers": {
    "jb-orchestrator": {
      "command": "uv",
      "args": ["run", "--project", "<repository-path>", "jb-mcp"],
      "env": {
        "JB_CONTROL_PLANE_URL": "http://127.0.0.1:8000",
        "JB_API_TOKEN": "<service-account-token>"
      }
    }
  }
}
```

호스트별 설정 파일 형식은 다를 수 있지만 command, args, env의 의미는 같습니다.
OpenClaw가 MCP stdio server 등록을 지원하는 배포에서는 같은 구성을 사용하고, 직접 MCP를
지원하지 않는 배포에서는 ORCH-026 REST ingress를 호출하는 얇은 adapter를 사용합니다.
MCP 서버는 `JB_API_TOKEN`이 없으면 시작하지 않습니다.

```powershell
uv run jb mcp check --project-id <project-uuid>
uv run jb mcp config --project-path <repository-path>
uv run jb mcp smoke --project-id <project-uuid>
```

첫 명령은 현재 token의 API 연결 및 프로젝트 권한을 확인합니다. 두 번째 명령은 실제 token을
노출하지 않고 범용 stdio MCP host 설정을 출력합니다. 세 번째 명령은 `jb-mcp`를 실제 별도
프로세스로 실행해 MCP 초기화, 도구 목록, 인증된 프로젝트 조회를 15초 안에 검증합니다.
OpenClaw 역할 분리와 Control Agent 지시문은 `docs/openclaw-control-agent.md`에 정리되어
있습니다.

제공 도구는 `get_project`, `list_project_requests`, `list_project_workflows`,
`list_workflow_options`, `dispatch_request`, `get_request`, `get_run`,
`get_workflow_execution`, `list_artifacts`, `approve_workflow_node`, `cancel_run`입니다.
`list_workflow_options`에서 정확한 key/version을 확인한 뒤 `dispatch_request`에 함께 전달하면
해당 요청만 선택한 Workflow를 사용한다. 둘 다 생략하면 프로젝트 기본 binding을 사용한다.
실제 접근 가능 범위는 token을 발급할 때 부여한 프로젝트 scope와 permission으로 제한됩니다.

Executor adapter packages expose a no-argument factory in their `pyproject.toml`:

```toml
[project.entry-points."jb_orchestrator.executors"]
codex = "jb_codex_executor:create_executor"
```

The factory returns an object implementing the async `TaskExecutor.execute(claim)` contract.
Its entry-point name must match the workflow node's `executor_key`.
For model-routed tasks, the executor returns provider-reported input and output token usage in
`TaskResult.usage`; configured project budgets require this usage for actual settlement.

Skill registration stores immutable metadata; workers fetch and verify the files only when a
referencing task is claimed. Local sources must be below `JB_SKILL_LOCAL_ROOT`. Remote Git and
archive hosts must be explicitly listed in the JSON array `JB_SKILL_ALLOWED_REMOTE_HOSTS`.
Verified packages are stored below `JB_SKILL_CACHE_DIR`, and executors receive only their
verified entrypoint paths.

The API exposes:

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/projects`
- `GET /v1/projects`
- `GET /v1/projects/{project_id}`
- `GET /v1/projects/{project_id}/requests`
- `GET /v1/projects/{project_id}/workflow-executions`
- `GET /v1/projects/{project_id}/events/stream`
- `POST /v1/projects/{project_id}/requests`
- `PUT /v1/projects/{project_id}/workflow-binding`
- `GET /v1/projects/{project_id}/workflow-binding`
- `POST /v1/projects/{project_id}/dispatches`
- `GET /v1/projects/{project_id}/workflow-options`
- `GET /v1/requests/{request_id}`
- `GET /v1/requests/{request_id}/runs`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/approve`
- `POST /v1/runs/{run_id}/cancel`
- `POST /v1/skills`
- `GET /v1/skills`
- `GET /v1/skills/{key}?version={version}`
- `POST /v1/models`
- `GET /v1/models`
- `GET /v1/models/{key}?version={version}`
- `PUT /v1/projects/{project_id}/budget`
- `GET /v1/projects/{project_id}/budget`
- `GET /v1/projects/{project_id}/usage`
- `POST /v1/workflows`
- `GET /v1/workflows`
- `GET /v1/workflows/{key}?version={version}`
- `POST /v1/runs/{run_id}/workflow`
- `GET /v1/runs/{run_id}/workflow`
- `GET /v1/workflow-executions/{execution_id}`
- `GET /v1/workflow-executions/{execution_id}/artifacts`
- `POST /v1/workflow-executions/{execution_id}/approvals/{node_key}`
- `POST /v1/workflow-executions/{execution_id}/cancel`
- `GET /v1/external-executions`
- `GET /v1/external-executions/events/stream`
- `GET /v1/external-executions/{execution_id}`

외부 런타임 실행은 PostgreSQL 원장을 기준으로 조회합니다. 목록 API는
`workflow_execution_id`, `run_id`, `status`, `limit` 필터를 지원하므로 Jarvis 같은
클라이언트가 폴링으로 현재 상태를 표시할 수 있습니다. 각 상태 전이는 동일 트랜잭션에서
작은 도메인 이벤트도 기록합니다. SSE 엔드포인트는 저장된 이벤트를 먼저 재생한 뒤 새
이벤트를 전달하며, 재연결 시 `Last-Event-ID` 이후부터 이어서 받을 수 있습니다.

프로젝트에는 정확한 Workflow 정의 버전을 기본값으로 연결할 수 있습니다. 사용자는
`POST /v1/projects/{project_id}/dispatches`에 요청을 한 번 보내면 User Request, Run,
Workflow Execution이 하나의 트랜잭션에서 생성됩니다. 요청 본문의 선택적인 `workflow`에
`definition_key`와 `definition_version`을 함께 지정하면 프로젝트 binding을 변경하지 않고
그 요청만 다른 정확한 버전으로 실행한다. 생략하면 기존처럼 기본 binding을 사용한다.
선택된 정의와 요청 문맥은 실행 스냅샷에 고정되므로 이후 프로젝트 바인딩을 변경해도 이미
시작된 실행에는 영향을 주지 않습니다. 기존의 요청 생성 및 수동 Workflow 시작 API도 명시적
실행이 필요한 도구를 위해 계속 제공됩니다. Dispatch 호출에는 프로젝트 범위에서 고유한
`Idempotency-Key` 헤더가 필수입니다. 같은 key와 payload 및 Workflow 선택을 재전송하면
응답의 `replayed`가 `true`이고 최초 실행을 그대로 반환합니다. 같은 key를 다른 요청 내용이나
Workflow 선택에 사용하면 `409 Conflict`가 반환됩니다.
입력 어댑터는 선택적으로 `X-JB-Ingress-Key`, `X-JB-External-Request-ID`,
`X-JB-Actor-ID`, `X-JB-Conversation-ID`를 전달할 수 있습니다. 멱등성 key는 프로젝트와
ingress 안에서 고유하므로 OpenClaw와 Jarvis가 우연히 같은 key를 사용해도 서로 충돌하지
않습니다. origin 값은 호출자가 주장한 출처 메타데이터이고 인증된 identity와 분리됩니다.
인증을 활성화하면 bearer service account의 permission과 DB에서 계산한 project scope가
모든 `/v1` 요청에 적용됩니다. 프로젝트가 정해지지 않는 전역 목록 및 catalog API는
`all_projects` 계정만 사용할 수 있습니다.

프로젝트 관찰 API는 DB 관계를 기준으로 Request, Run, Workflow Execution을 조회합니다.
Jarvis는 `GET /v1/projects/{project_id}/events/stream` 하나로 프로젝트에 속한 상태 변화를
받고, 연결이 끊기면 마지막 event UUID를 `Last-Event-ID`로 보내 이어받을 수 있습니다.
현재 상태의 복구는 목록 API가, 이후 변화의 전달은 SSE가 담당하므로 GUI 자체 캐시는
진실의 원천이 아닙니다.

## Declarative bundles

`orchestrator.yaml`은 실행 코드나 secret이 아니라 Control Plane에 등록할 버전 고정 구성을
기술한다. 기본 예시는 `examples/bundles/basic-openclaw.yaml`에 있다.

```powershell
uv run jb bundle validate examples/bundles/basic-openclaw.yaml
uv run jb bundle plan examples/bundles/basic-openclaw.yaml
uv run jb bundle apply examples/bundles/basic-openclaw.yaml
```

`validate`는 API 연결 없이 실행된다. `plan`과 `apply`는 `JB_CONTROL_PLANE_URL`과
`JB_API_TOKEN`을 사용한다. 새 Project와 전역 catalog를 등록하려면 `project.admin` 및
`all_projects` 범위의 관리용 서비스 계정이 필요하다. Bundle 외부의 exact-version 참조는
`external_dependencies`에 표시되며, 서버에 존재하지 않으면 plan이 conflict를 반환한다.

동일한 identity와 동일한 내용은 `unchanged`로 재적용할 수 있다. 동일한 Project key 또는
`key@version`에 다른 내용이 있으면 기존 값을 덮어쓰지 않고 실패하므로 version을 올려야 한다.
`apply` 도중 네트워크가 끊기면 같은 파일로 다시 `plan`한 뒤 `apply`하여 수렴시킨다.

새 구성을 처음 작성할 때는 Starter Kit을 기존 경로를 덮어쓰지 않는 새 디렉터리에 생성한다.

```powershell
uv run jb bundle init jb-orchestration
Set-Location jb-orchestration
$env:JB_SKILL_LOCAL_ROOT = (Resolve-Path skills)
uv run jb bundle validate orchestrator.yaml
```

Starter Kit에는 기획만 실행하는 구성, bounded repair loop를 포함한 표준 전달 구성, 두 검증을
동시에 수행하는 fork/join 구성이 함께 들어 있다. 이들은 선택 가능한 예제이며 실행 순서를
강제하는 내장 lifecycle이 아니다. `apply` 전에 Project URL, 기본 Workflow binding과 OpenClaw
agent 설정을 실제 환경에 맞게 수정한다.

Task 결과의 구조화된 값으로 다음 노드를 선택하려면 같은 outcome에 조건 간선을 선언한다.
조건은 출력 계약 검증이 끝난 Artifact에 적용된다.

```yaml
edges:
  - source: verify
    outcome: success
    target: review
    condition: {path: /verdict, equals: approve}
  - source: verify
    outcome: success
    target: repair
    condition: {path: /verdict, equals: changes_requested}
```

한 source/outcome의 조건들은 동일한 JSON Pointer 경로와 서로 다른 scalar 값을 사용해야 한다.
조건 없는 간선을 하나 추가하면 일치하지 않을 때의 default가 된다. default도 일치 조건도
없으면 Workflow는 재현 가능한 실패로 종료하며 임의의 경로를 선택하지 않는다.

## Quality checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Jarvis는 별도 Node 품질 게이트를 사용합니다.

```powershell
Set-Location apps/jarvis
npm ci --no-audit --no-fund
npm run format:check
npm run lint
npm test
npm run build
```

전체 로컬 경계는 반드시 비어 있는 일회용 PostgreSQL test database에서 검증합니다. 다음 명령은
smoke 전용 executor를 임시 설치하고 Control Plane, Worker와 Jarvis를 실제 별도 process로
실행합니다.

```powershell
$env:JB_ENVIRONMENT = "test"
$env:JB_DATABASE_URL = "postgresql+asyncpg://jb_orchestrator:jb_orchestrator@localhost:5432/jb_orchestrator"
uv run alembic upgrade head
uv run --with-editable tools/system-smoke-executor jb system smoke
```

이 명령은 지정한 database에 고유한 smoke project와 service account를 생성하므로 개발 또는
운영 database에는 실행하지 않습니다.

## Branch strategy

- `main`: production-ready releases
- `develop`: integration branch
- `feature/ORCH-<number>-<description>`: feature work
- `release/<version>`: release stabilization
- `hotfix/ORCH-<number>-<description>`: urgent production fixes

Commits follow Conventional Commits, for example:

```text
feat(workflow): 노드 상태 전이 추가
test(api): 요청 생명주기 검증
docs(adr): 작업 큐 결정 기록
```
