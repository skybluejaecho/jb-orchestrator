# Jarvis local dashboard

Jarvis는 jb-orchestrator의 진실의 원천이 아니라 로컬 관찰 UI다. 프로젝트, 요청 및
Workflow 상태를 Control Plane API에서 읽고 프로젝트 SSE stream으로 변경을 감지한다.

## Local setup

Jarvis는 프로젝트 상태를 조회하고 사용자의 요청을 제출하며 명시적인 승인 결정을
처리하고 실행을 취소하며 작업공간 검토 명령을 등록하므로 `project.read`,
`request.dispatch`, `workflow.approve`, `run.cancel`, `workspace.manage`, `scm.publish`,
`all_projects` 범위를
가진 전용 서비스 계정을 사용한다.

```powershell
uv run jb auth issue `
  --key jarvis-local `
  --name "Jarvis Local Dashboard" `
  --permission project.read `
  --permission request.dispatch `
  --permission workflow.approve `
  --permission run.cancel `
  --permission workspace.manage `
  --permission scm.publish `
  --all-projects

Copy-Item apps/jarvis/.env.example apps/jarvis/.env.local
```

발급된 token을 `.env.local`의 `JARVIS_API_TOKEN`에 넣은 뒤 실행한다.

```powershell
Set-Location apps/jarvis
npm install
npm run dev
```

브라우저에는 API token을 전달하지 않는다. Vinext server route가 token을 보관하고
Control Plane으로 요청을 proxy한다. 요청 작성 화면은 프로젝트 기본 Workflow 또는 등록된
정확한 Workflow 버전을 선택할 수 있다. 선택하지 않으면 기본 binding을 사용하며 선택해도
프로젝트 기본값 자체는 변경되지 않는다. 선택한 Workflow의 노드, Phase Pack, Skill source는
제출 전에 읽기 전용 구성 미리보기로 표시된다. 등록된 최신 Skill은 task 노드마다 선택적으로
추가할 수 있으며 해당 요청의 Snapshot에만 고정된다. 요청 제출은 `jarvis` ingress와 멱등성 key를 사용한다.
실행을 선택하면 노드 상태와 산출물뿐 아니라 Control Plane의 외부 실행 원장도 함께 조회한다.
외부 런타임 영역에는 노드별 executor, agent ID, session key, run ID와 현재 상태가 표시된다.
표시 값은 OpenClaw 자체 메모리를 추측한 것이 아니라 Worker가 DB에 기록한 실행 매핑이다.
격리된 Git worktree가 할당된 실행은 생성된 branch, base ref와 로컬 path도 함께 표시한다.
안전한 cleanup이 완료되면 DB의 release 시각을 반영해 해당 worktree가 정리됐음을 표시한다.
범위가 등록된 worktree는 프로젝트 기본 브랜치를 기준으로 검사를 요청하고, 외부 실행이
종료된 뒤 전체 외부 실행 UUID를 정확히 입력해야 정리를 요청할 수 있다. 실제 Git 작업은
동일한 scope의 `jb-openclaw workspace worker`가 수행하며 Jarvis는 작업 상태를 낙관적으로
변경하지 않는다.
종료되었고 아직 정리되지 않은 worktree는 GitHub PR 게시 요청을 등록할 수 있다. 대상 브랜치,
PR 제목과 본문을 확인한 뒤 요청하며, Jarvis는 PostgreSQL 게시 원장의 대기·처리·성공·실패
상태를 표시한다. 성공 URL은 HTTPS일 때만 외부 링크로 제공된다. 실제 push와 PR 생성은 동일한
scope를 담당하는 `jb-scm-worker`가 수행한다.
승인 대기 노드는 승인 또는 반려를 한 번 더 확인한 뒤 처리한다. 진행 중인 실행을 취소하려면
화면에 표시된 실행 식별 문구를 정확하게 입력해야 한다. Jarvis는 로컬 실행만 지원하며 외부
네트워크 공개나 Sites 배포는 별도 사용자 인증 계층을 추가하기 전에는 허용하지 않는다.

## Checks

```powershell
npm run format:check
npm run lint
npm test
npm run build
```

계약 테스트는 Control Plane을 실제로 실행하지 않고 server proxy의 인증 header, 오류 전달,
dispatch payload, 멱등 재시도 규칙, 실행 상세·산출물·외부 실행 조회, 승인 결정, 실행 취소와
SCM 게시 계약을 검증한다. 동일한 검사는 GitHub Actions의 `Jarvis` job에서 모든 `develop` 및
`main` PR과 push에 실행된다.

## System smoke

실제 PostgreSQL, Control Plane, Worker와 Jarvis process 사이의 계약은 저장소 root에서 다음
명령으로 검증한다. 반드시 비어 있는 일회용 test database를 사용해야 한다.

```powershell
$env:JB_ENVIRONMENT = "test"
uv run alembic upgrade head
uv run --with-editable . --with-editable adapters/github --with-editable tools/system-smoke-executor jb system smoke
```

smoke executor는 외부 agent runtime을 호출하지 않으며 `JB_ENVIRONMENT=test`가 아니면 시작을
거부한다.
