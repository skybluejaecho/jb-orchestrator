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

ORCH-044 exposes external agent ownership in Jarvis:

- execution detail loads the matching external execution ledger records from the Control Plane
- each record identifies its Workflow node, executor, external agent, session, run, and status
- provider failure reasons remain visible next to the responsible external run
- empty states distinguish nodes not yet assigned to an external runtime
- the server-side proxy retains the service-account token and returns no provider terminal payloads

ORCH-045 adds opt-in Git worktree isolation for OpenClaw tasks:

- mutating parallel nodes can run in deterministic execution/node/visit-specific worktrees
- retries validate and reuse the same branch and path instead of creating duplicate workspaces
- repository access is restricted to configured roots and worktrees must live outside repositories
- explicit base refs keep Git Flow branch origins operator-controlled
- workspace path, branch, and base ref are persisted in the external execution ledger and shown in Jarvis
- completed branches remain available for deliberate review and merge; cleanup is never automatic

ORCH-046 adds a guarded worktree review and release lifecycle:

- `jb-openclaw workspace inspect` reports cleanliness and merge readiness against one local target ref
- cleanup requires a terminal external run, clean files, an already-merged HEAD, and exact UUID confirmation
- the linked worktree and exact local branch are removed without fetching, pushing, merging, or opening a PR
- branch deletion uses an expected-HEAD Git reference update to avoid deleting a concurrently changed ref
- successful cleanup records a durable release timestamp and event, which Jarvis displays through SSE refresh

ORCH-047 adds a durable workspace operation queue:

- clients submit idempotent inspect or explicitly confirmed cleanup commands to the Control Plane
- PostgreSQL owns pending, claimed, succeeded, and failed operation state plus audit events
- an opaque scope derived from the worktree root and repository allowlist routes work to a compatible host
- `jb-openclaw workspace worker` claims operations with leases and executes the ORCH-046 safety gates
- `workspace.manage` is independent from read, dispatch, approval, and cancellation permissions
- project SSE includes workspace operation lifecycle changes without making Jarvis a state owner

ORCH-048 adds guarded workspace operations to Jarvis:

- each managed external execution shows durable inspect and cleanup operation history
- the project default branch seeds an editable local merge target ref
- cleanup is available only for terminal executions and requires the complete external execution UUID
- a same-origin Jarvis route validates commands while keeping the Control Plane token server-side
- pending and claimed work is shown without optimistic completion, then refreshed from project SSE
- pre-ORCH-047 assignments remain clearly routed to the direct OpenClaw CLI

ORCH-049 defines a provider-neutral SCM publication boundary:

- `ScmPublisher.publish_review` publishes one source branch for human review without merging it
- requests carry repository, branch, review text, and idempotency identity but never credentials
- results retain provider-neutral review URL and stable provider identifiers
- installed GitHub, GitLab, or other adapters use the `jb_orchestrator.scm_publishers` entry-point
  group and are selected by an explicit provider key
- publication remains separate from workspace cleanup, remote merge, and branch deletion

ORCH-050 adds a durable SCM publication ledger:

- publication requests derive repository and source branch from trusted Project and
  ExternalExecution records
- only terminal, unreleased managed workspaces can be submitted for remote review
- PostgreSQL stores idempotent pending, claimed, succeeded, and failed publication state
- workers claim by explicit provider key and opaque workspace scope with expiring leases
- scm.publish is independent from project read, dispatch, approval, cancellation, and workspace
  maintenance permissions
- project event streams include publication lifecycle changes without storing SCM credentials

ORCH-051 executes durable publications through installed adapters:

- jb-scm-worker serves one opaque workspace scope and discovers provider entry points at startup
- claimed work is routed only when both its provider key and workspace scope match the worker
- the runtime reloads trusted worktree state before passing its path to the publisher
- provider execution is bounded by a timeout shorter than the database claim lease
- provider, repository, and branch identifiers must match before success is recorded
- adapter errors, timeouts, state drift, and mismatched results become durable failure records

ORCH-052 adds the first concrete SCM publisher for GitHub:

- the separately installed github entry point performs a non-force push of the exact worktree HEAD
- repository URL, worktree root, clean state, current branch, remote identity, and Git refs are
  validated before mutation
- exact open head/base pull requests are reused, including one bounded HTTP 422 race recovery
- the GitHub API token remains adapter-owned and is never injected into Git commands or URLs
- response bodies and authorization data are excluded from durable failure messages
- merge, force-push, branch deletion, and workspace cleanup remain explicit separate operations

ORCH-053 extends the process-level system smoke through the complete SCM publication boundary:

- a disposable feature worktree pushes its exact HEAD to a local bare Git remote
- a loopback GitHub API stub records the pull-request creation without external network mutation
- the Control Plane persists the request before a separately started SCM worker claims it
- the worker discovers the real GitHub adapter entry point and writes the provider result back
- insecure HTTP remains disabled except for an explicit loopback fixture in `JB_ENVIRONMENT=test`

ORCH-054 exposes the durable SCM publication flow in the local Jarvis dashboard:

- terminal managed worktrees can request a GitHub pull request without exposing API credentials
- target branch, pull-request title, and body remain explicit operator inputs
- pending, claimed, succeeded, and failed records are rendered from the Control Plane ledger
- completed review URLs become links only after Jarvis validates their HTTPS scheme
- project SSE events refresh publication state without making the browser predict completion

ORCH-055 adds explicit, ledger-preserving recovery for failed SCM publications:

- every worker claim increments a durable attempt counter
- only failed publications can be reset to pending; active retries replay safely
- succeeded publications and released or changed worktrees remain non-retryable
- project-scoped authorization resolves a publication back through its external execution
- Jarvis shows attempt counts and offers retry only for eligible failed records
- the system smoke proves first-attempt failure followed by a successful Jarvis-triggered retry

ORCH-056 adds provider-neutral failure classification before any automatic retry policy:

- durable failures retain a stable code and retryable decision next to the human-readable reason
- adapters report typed failures without leaking provider-specific exceptions into the Control Plane
- runtime timeouts and result or workspace validation failures receive deterministic classifications
- GitHub 408, 429, 5xx, and transport failures are distinguished from permanent provider rejection
- Jarvis shows whether retry is reasonable or operator investigation is required
- explicit retry remains operator-controlled; bounded automatic backoff is a separate policy

ORCH-057 adds opt-in, bounded automatic recovery for transient SCM publication failures:

- automatic retries are disabled by default and configured explicitly on each SCM worker
- only failures classified as retryable receive a durable next-attempt timestamp
- exponential delays are capped and the allowed retry count is persisted with the publication
- due retries reclaim the same publication ID and continue its attempt counter
- exhausted or permanent failures remain terminal instead of polling indefinitely
- Jarvis renders the durable schedule while the system smoke proves recovery without browser action

ORCH-058 adds explicit operator controls for scheduled SCM publication retries:

- scheduled retries can be cancelled without removing the failure reason or attempt history
- repeated cancellation is idempotent while active or completed publications reject the command
- the existing manual retry command converts a scheduled failure into immediately claimable work
- cancellation and worker claim serialize through the same locked publication record
- project-scoped `scm.publish` authorization protects both cancellation and immediate retry
- Jarvis exposes `예약 취소` and `지금 재시도` and refreshes peers from durable events

ORCH-059 adds a durable, per-attempt SCM publication ledger:

- every worker claim creates an atomic attempt record beside the publication state transition
- initial, manual, automatic, and expired-lease recovery claims remain distinguishable
- each attempt retains its worker, timing, terminal result, and provider-neutral failure evidence
- the read API returns newest attempts first without exposing internal lease tokens
- Jarvis loads the attempt timeline on demand instead of reconstructing history from browser state
- the system smoke proves an initial provider failure followed by a successful manual recovery

ORCH-060 adds durable process presence for every worker type:

- each process start creates an immutable worker instance identity beside its human-readable ID
- execution, OpenClaw workspace, and SCM workers publish capabilities and optional workspace scope
- idle workers heartbeat independently from active task leases
- graceful exits become stopped while missed heartbeats are derived as stale without rewriting history
- the Control Plane lists recent worker instances and Jarvis renders online, stale, and stopped status
- the system smoke verifies execution and SCM worker lifetimes through the authenticated Jarvis proxy

ORCH-061 adds project-scoped worker readiness diagnostics:

- every READY workflow node is matched against current execution-worker capabilities
- repeated process lifetimes with the same worker ID are reduced to the latest instance
- missing capabilities are distinguished from known workers that are stale or stopped
- the report retains executor coverage and exact workflow/node identifiers without changing claims
- project-scoped read authorization protects the diagnostic API
- Jarvis explains blocked assignments and refreshes from both project events and bounded polling

ORCH-062 adds deterministic, request-scoped Workflow recommendations:

- prompt terms and stable intent categories are matched against complete Workflow compositions
- exact-version candidates include scores, matched evidence, and project-default context
- policy version and prompt digest are persisted with every recommendation as a project event
- high-confidence recommendations may select directly while ambiguous results require confirmation
- dispatch validates the recommendation project, prompt, and selected candidate before execution
- Jarvis presents ranked candidates without becoming the source of truth for selection policy

ORCH-063 adds durable Worker readiness alerts:

- each unassignable READY-node occurrence opens at most one durable alert
- repeated evaluations update the same alert while preserving its first detection time
- recovered assignments resolve alerts without deleting their history
- project events record alert creation, reason changes, and resolution for SSE consumers
- configurable duration thresholds distinguish warning from critical conditions
- Jarvis shows persisted severity, elapsed time, and capability-specific recovery guidance

ORCH-064 moves Worker readiness evaluation into an observable server-side monitor:

- a dedicated process evaluates every active project without depending on an open Jarvis browser
- the monitor registers its own process lifetime and heartbeat in the shared Worker ledger
- repeated cycles preserve alert identity and emit one durable event when an alert becomes critical
- archived projects are excluded and each cycle has an explicit project bound
- Jarvis reads the resulting ledger without mutating orchestration state
- the critical transition provides a stable source event for later notification adapters

ORCH-065 gives MCP Control Agents project-scoped Worker readiness parity:

- `get_worker_readiness` exposes the same PostgreSQL-backed diagnostic view used by Jarvis
- the MCP tool is explicitly read-only and requires only the existing `project.read` permission
- capability coverage, active and resolved alerts, severity, age, and recovery guidance remain intact
- OpenClaw instructions use the tool when READY work is not progressing without implying remediation
- the protocol E2E test proves the authenticated MCP-to-Control-Plane path

ORCH-066 hardens Worker readiness monitoring for multi-process operation:

- keyset pagination moves each bounded cycle to the next active-project page and wraps at the end
- a PostgreSQL transaction advisory lock serializes alert transitions for each project
- diagnostics and alert/event mutation share one transaction while a project lock is held
- one project failure is recorded in the cycle result without stopping later project evaluations
- structured cycle logs expose attempted, succeeded, failed, and remaining-page information
- deterministic repository and runtime tests prove stable pagination, lock-safe mutation, and fair sweeps

ORCH-067 adds durable notification subscriptions and a delivery outbox:

- projects register provider-neutral destinations by opaque reference without persisting credentials
- subscriptions explicitly select alerted, critical, and resolved Worker-readiness transitions
- supported readiness events create pending delivery intents in the same PostgreSQL transaction
- immutable delivery snapshots retain the destination, payload, source event, alert, and idempotency key
- unique subscription/event pairs suppress duplicate delivery creation across repeated evaluations
- `notification.manage` protects subscription changes while project readers can inspect delivery history
- disabling a subscription affects future events without deleting already-persisted delivery intents
- no network delivery occurs until a separately installed Notification Worker and provider are added

ORCH-068 adds the provider-neutral Notification Worker boundary:

- `jb-notification-worker` discovers installed adapters from the
  `jb_orchestrator.notification_providers` entry-point group
- PostgreSQL claims are provider-scoped and protected by row locks plus expiring lease tokens
- an expired claim can be recovered by another process while stale lease holders cannot finish it
- adapters receive an opaque destination, immutable payload, and stable idempotency key
- successful output or a stable failure category is persisted as delivery evidence
- provider calls are bounded by a timeout shorter than the claim lease
- the Worker registers provider keys as capabilities in the shared process-presence ledger
- concrete network providers remain independently installable adapters

ORCH-069 adds the first installable notification provider:

- `adapters/webhook` registers the `webhook` provider without coupling it to the core package
- opaque destination references resolve to endpoint URLs and optional HMAC secrets only in the
  Worker environment
- Webhook requests carry a canonical JSON envelope, delivery metadata, and an idempotency key
- optional `X-JB-Signature-256` protects the exact request body with HMAC-SHA256
- production endpoints require HTTPS; insecure loopback HTTP is restricted to the test environment
- response bodies, endpoint URLs, and signing secrets are never persisted as delivery evidence
- transport, throttling, server, and rejection failures map to stable provider-neutral categories
- the process smoke proves signed delivery and the Notification Worker presence lifecycle

ORCH-070 adds durable notification attempt evidence and operator-controlled recovery:

- every claim creates an immutable-numbered attempt with its worker, trigger, and timestamps
- attempt triggers distinguish initial delivery, manual retry, and expired-lease recovery
- lease recovery closes the abandoned attempt with a stable `lease_expired` failure before claiming
  a new attempt
- success and failure evidence is retained per attempt instead of being overwritten on the Delivery
- failed Deliveries can be returned to `pending` without changing payload or idempotency identity
- pending or claimed retry requests are idempotent while succeeded Deliveries cannot be retried
- project-scoped retry requires `notification.manage`; attempt history remains readable to project
  readers without exposing lease tokens
- the process smoke proves an initial Webhook failure followed by a successful manual retry

ORCH-071 adds opt-in bounded automatic retry for transient notification failures:

- automatic retry is disabled by default and allows at most ten retries after the initial attempt
- only provider unavailability and timeouts are retryable; rejected and unexpected failures remain
  terminal
- retry schedules survive Worker restarts through durable `next_attempt_at` state
- exponential backoff grows from the configured base delay without exceeding its maximum
- due retries preserve the Delivery identity and create an `automatic` Attempt
- explicit manual retry clears any automatic schedule and remains available to operators

ORCH-072 adds an explicit operator control for scheduled notification retries:

- `POST /v1/projects/{project_id}/notification-deliveries/{delivery_id}/automatic-retry/cancel`
  removes a pending automatic schedule
- cancellation preserves the failed status, reason, classification, and complete Attempt history
- repeated cancellation is idempotent while active and succeeded Deliveries return a conflict
- cancellation is project-scoped, requires `notification.manage`, and is audited with its actor
- operators can still use the existing retry endpoint to run the same Delivery immediately

ORCH-073 brings notification delivery operations into Jarvis without moving execution ownership:

- the project dashboard reads recent Delivery state and expandable Attempt history from the
  Control Plane
- failed Deliveries expose an explicit immediate retry, while scheduled retries also expose a
  separate cancellation command
- notification Domain Events refresh the panel; the browser never invents delivery state or runs
  its own retry timer
- Jarvis server routes keep the service-account token out of the browser and preserve project scope
- the Notification Worker remains the only component that claims and sends Delivery records

ORCH-074 adds provider-neutral notification subscription management to Jarvis:

- operators can register a provider key, opaque destination reference, and supported readiness
  events for the selected project
- existing subscriptions expose event-filter editing and explicit enable or disable controls
- endpoint URLs and secrets remain exclusively in the Notification Worker environment
- Jarvis validates the bounded event vocabulary before proxying changes with `notification.manage`
- subscription Domain Events refresh the server-backed view without optimistic local ownership

ORCH-075 extends the real-process acceptance boundary through Jarvis notification routes:

- the smoke creates and configures subscriptions through the running Jarvis server
- Delivery listing, Attempt inspection, automatic retry cancellation, and immediate retry all use
  Jarvis proxies instead of bypassing them through direct Control Plane calls
- the Notification Worker schedules a bounded retry after the intentional first Webhook failure
- the test proves Jarvis authorization and payload translation across PostgreSQL and real processes
- the default per-process readiness timeout is 60 seconds to accommodate a cold Vinext startup

ORCH-076 improves Jarvis notification operations without tightening orchestration coupling:

- Delivery history can be filtered by status, provider, and event type
- scheduled retries and failures are prioritized ahead of active and successful deliveries
- subscription cards compare provider keys with durable Notification Worker capabilities
- online, delayed or stopped, and missing provider support are shown as distinct diagnostics
- provider diagnostics remain advisory, so operators can configure subscriptions before deployment
- Worker presence labels now cover Notification and readiness-monitor processes explicitly

ORCH-077 makes first-release readiness reproducible locally and visible as one CI decision:

- `jb system release-check` runs the locked Python, Jarvis, and OpenClaw contract gates in a stable
  fail-fast order
- `--include-system-smoke` appends migrations and the complete real-process acceptance boundary
- the full mode fails closed unless `JB_ENVIRONMENT=test` is explicitly configured
- each command has a bounded timeout and failures retain the final diagnostic output
- CI aggregates every independent job into one `Release readiness` status for branch protection

ORCH-078 adds a role-scoped deployment preflight before processes are started:

- `jb system preflight` checks every deployment role or a repeated `--role` subset
- PostgreSQL connectivity and exact Alembic head parity are checked for database-owning processes
- Control Plane authentication and remote transport rules fail closed in production
- installed task executors, SCM publishers, and notification providers are loaded with their real
  configuration contracts
- OpenClaw bridge, Node.js, Gateway transport, TLS pin, and credential presence are diagnosed
- MCP and Jarvis verify server-side Control Plane URLs and API token presence without rendering secrets
- structured `pass`, `warning`, and `fail` results support both people and process supervisors

ORCH-079 adds a reproducible single-host runtime composition:

- one non-root Python image packages the Control Plane, migrations, Workers, OpenClaw bridge, GitHub
  publisher, and Webhook notifier
- a separate non-root Jarvis image builds once and serves the Vinext production output
- PostgreSQL, migrations, API, and readiness monitoring form the default core deployment
- Compose profiles independently enable task execution, SCM publication, notifications, Jarvis, and
  one-shot administration
- provider credentials are injected only into the process that owns each external capability
- PostgreSQL, OpenClaw device identity, rebuildable skill cache, repositories, and worktrees use
  explicit and distinct persistence boundaries
- CI validates every optional Compose profile without pulling or starting deployment images

ORCH-080 separates server ownership from the local Jarvis client without splitting repositories:

- the server composition runs PostgreSQL, migrations, the Control Plane, readiness monitoring, and
  optional Workers without publishing a Jarvis UI
- the API binds to server loopback by default and can be explicitly bound to a private VPN interface
- the Jarvis composition runs independently on a trusted workstation and publishes only to
  `127.0.0.1`
- Jarvis connects to the remote Control Plane using a distinct least-privilege service-account token
- CI and contract tests validate the server and client compositions independently

ORCH-081 establishes a guarded container image release boundary:

- CI builds the Runtime and Jarvis images and verifies their non-root execution contracts
- only stable `vX.Y.Z` tags whose component versions agree may publish packages
- release tags must point to commits contained in `main`
- GHCR receives explicit SemVer and source-commit tags without a mutable `latest` tag
- published images include OCI metadata, provenance, and an SBOM
- server and Jarvis operators independently pin the exact image version they deploy

ORCH-082 separates stable service-account identity from revocable bearer credentials:

- one service account can own multiple credentials without duplicating permissions or project scope
- each credential has independent expiration, revocation, and last-used timestamps
- revoking an account still disables every credential that belongs to it
- tokens issued before this migration remain valid because their existing identifier and digest are
  backfilled as the account's first credential
- the credential identifier is included in authenticated principals and issuance output so later
  audit and rotation workflows can identify the exact secret that was used
- credential rotation and revocation management endpoints are intentionally deferred to a separate
  operational API/CLI change

ORCH-083 exposes guarded service-account credential rotation:

- only an authenticated `project.admin` account with `all_projects` scope can use the management API
- operators can issue, list, and individually revoke credentials without changing account policy
- list responses expose lifecycle metadata but never token digests or bearer secrets
- the new bearer token is returned only by the issue response
- CLI credential commands use the Control Plane API, while the original account issue command remains
  a direct-database bootstrap boundary

ORCH-084 records credential lifecycle administration in the append-only event ledger:

- credential issuance, individual revocation, and account-wide revocation are committed with an audit event
- authenticated management events identify both the acting service account and exact credential
- bootstrap operations remain attributable as system actions without inventing an operator identity
- audit responses never contain bearer tokens or token digests
- latest-first sequence pagination provides bounded operational history without a second audit database
- successful authentication continues to update `last_used_at` without emitting a high-volume event

ORCH-085 closes the process-level credential rotation boundary in the release smoke test:

- the smoke setup account issues a replacement credential through the live authenticated API
- the replacement token must authenticate before the original credential is revoked
- the revoked token must be rejected immediately while the replacement remains active
- credential inventory must expose the retired and active states without returning secret material
- the audit ledger must attribute issuance to the original credential and revocation to its replacement
- the structured smoke result reports only credential identifiers and verification states, never tokens

ORCH-086 exposes a guarded service-account operations inventory:

- global administrators can list and inspect stable account identity, permissions, scope, and activation
- key-ordered cursor pagination and activation or key-prefix filters keep inventory reads bounded
- credential summaries distinguish lifecycle-active credentials from credentials actually usable by an enabled account
- active, expired, and revoked counts form a deterministic lifecycle partition at the inspection time
- latest issuance and use timestamps support operations without exposing bearer tokens or token digests
- API and CLI remain read-only; account creation, policy mutation, and automatic rotation stay outside this boundary

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
uv run jb-readiness-monitor
uv run jb-notification-worker --list-providers
uv run jb-notification-worker --automatic-retry-limit 2 `
  --automatic-retry-base-delay 30 --automatic-retry-max-delay 300
```

원격 Docker host에서 서버 역할을 운영하려면
[`deploy/server/README.md`](deploy/server/README.md)를 사용합니다. 사용자 PC에서 Jarvis를
실행하려면 [`deploy/clients/jarvis/README.md`](deploy/clients/jarvis/README.md)를 사용합니다.
두 구성은 서로 독립적으로 실행되며 Jarvis는 원격 서버에 UI port를 만들지 않습니다.
컨테이너 버전 발행 및 운영 host 갱신 절차는
[`docs/operations/container-image-release.md`](docs/operations/container-image-release.md)를 따릅니다.

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

추가 credential의 무중단 rotation에는 `project.admin`과 `all_projects`를 가진 운영자 token을
CLI의 `JB_API_TOKEN`으로 설정한 뒤 다음 명령을 사용합니다. 첫 명령에서 반환되는 새 token을
클라이언트 secret 저장소에 적용하고 정상 연결을 확인한 후에만 기존 credential을 폐기합니다.

```powershell
uv run jb auth credential issue <account-uuid> `
  --expires-at 2026-12-31T15:00:00Z
uv run jb auth credential list <account-uuid>
uv run jb auth credential audit <account-uuid> --limit 100
uv run jb auth credential revoke <account-uuid> <old-credential-uuid>
```

Credential 관리 API는 `JB_API_AUTH_ENABLED=true`일 때만 사용할 수 있습니다. 목록에는 token이나
digest가 포함되지 않으며 token 원문은 발급 응답에서 한 번만 표시됩니다.
전체 account 운영 현황은 동일한 global admin token으로 조회합니다. `active`는 credential 자체가
만료·폐기되지 않은 수이고, `usable`은 account 활성 상태까지 반영해 실제 인증 가능한 수입니다.

```powershell
uv run jb auth account list --enabled --key-prefix openclaw --limit 100
uv run jb auth account list --after-key openclaw-control --limit 100
uv run jb auth account show <account-uuid>
```

## Run

```powershell
uv run jb-api
uv run jb doctor
uv run jb skill digest skills/my-skill
uv run jb-worker --list-executors
uv run jb-scm-worker --list-publishers
uv run jb-readiness-monitor
uv run jb-mcp
# After installing at least one executor adapter:
uv run jb-worker --once
```

Jarvis 로컬 대시보드는 별도 터미널에서 실행합니다. 전용 서비스 계정에는 상태 조회와 요청
제출 외에 승인 기능을 사용할 경우 `workflow.approve`, 취소 기능을 사용할 경우 `run.cancel`,
작업공간 검사·정리 기능을 사용할 경우 `workspace.manage` 권한도 부여합니다. 사용자 인증
계층을 추가하기 전까지 외부 네트워크에 공개하거나 배포하지 않습니다.

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
`list_workflow_options`, `recommend_workflow`, `dispatch_request`, `get_request`, `get_run`,
`get_workflow_execution`, `list_artifacts`, `get_worker_readiness`,
`approve_workflow_node`, `cancel_run`입니다.
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

SCM publisher packages use a separate entry-point group:

    [project.entry-points."jb_orchestrator.scm_publishers"]
    github = "jb_github_publisher:create_publisher"

After installing a publisher, run one worker for the opaque scope emitted by the managed worktree
host. The operation timeout must remain shorter than the lease:

    uv run --with-editable . --with-editable adapters/github jb-scm-worker --workspace-scope <workspace-scope> --lease-seconds 300 --operation-timeout 240

Bounded automatic retry is opt-in. This example allows two retries after the initial attempt with
30 and 60 second delays, capped at five minutes:

    uv run --with-editable . --with-editable adapters/github jb-scm-worker --workspace-scope <workspace-scope> --automatic-retry-limit 2 --automatic-retry-base-delay 30 --automatic-retry-max-delay 300

The adapter receives repository and branch data plus the trusted current worktree path. It reads
credentials only from its own environment or secret store. The core worker never merges reviews,
deletes remote branches, or releases local worktrees.

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

동일한 릴리스 게이트를 저장소 root에서 한 번에 실행할 수 있습니다. 기본 모드는 외부 agent
runtime 없이 Python lock·품질·테스트, Jarvis 품질·테스트·빌드, OpenClaw protocol contract를
검증합니다.

```powershell
uv run jb system release-check
```

전체 process 경계까지 검증하려면 반드시 비어 있는 일회용 PostgreSQL test database를 지정합니다.

```powershell
$env:JB_ENVIRONMENT = "test"
$env:JB_DATABASE_URL = "postgresql+asyncpg://jb_orchestrator:jb_orchestrator@localhost:5432/jb_orchestrator"
uv run jb system release-check --include-system-smoke
```

## Deployment preflight

실행할 process와 같은 환경에서 전체 역할의 운영 준비 상태를 점검합니다. 기본 호출은 모든 역할을
검사하며 하나 이상의 필수 항목이 실패하면 JSON 보고서를 출력한 뒤 종료 코드 `1`을 반환합니다.

```powershell
uv run --with-editable . --with-editable adapters/openclaw `
  --with-editable adapters/github --with-editable adapters/webhook `
  jb system preflight
```

한 host에 배포할 역할만 선택하려면 `--role`을 반복합니다.

```powershell
uv run --with-editable . --with-editable adapters/openclaw `
  jb system preflight --role task-worker --role readiness-monitor

uv run jb system preflight --role mcp --role jarvis
```

지원 역할은 `control-plane`, `task-worker`, `scm-worker`, `notification-worker`,
`readiness-monitor`, `mcp`, `jarvis`다. 비밀번호, API token, Webhook secret, Gateway credential은
보고서에 포함되지 않는다. Preflight는 외부 API나 OpenClaw Gateway에 연결하지 않으며 실제 연결은
각 환경의 명시적인 acceptance 단계에서 확인한다.

전체 로컬 경계는 반드시 비어 있는 일회용 PostgreSQL test database에서 검증합니다. 다음 명령은
smoke 전용 executor, GitHub publisher와 Webhook notifier를 임시 설치하고 Control Plane,
Worker, SCM Worker, Notification Worker와 Jarvis를 실제 별도 process로 실행합니다.

```powershell
$env:JB_ENVIRONMENT = "test"
$env:JB_DATABASE_URL = "postgresql+asyncpg://jb_orchestrator:jb_orchestrator@localhost:5432/jb_orchestrator"
uv run alembic upgrade head
uv run --with-editable . --with-editable adapters/github --with-editable adapters/webhook `
  --with-editable tools/system-smoke-executor jb system smoke
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
