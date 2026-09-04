# Jarvis local dashboard

Jarvis는 jb-orchestrator의 진실의 원천이 아니라 로컬 관찰 UI다. 프로젝트, 요청 및
Workflow 상태를 Control Plane API에서 읽고 프로젝트 SSE stream으로 변경을 감지한다.

## Local setup

Jarvis는 프로젝트 상태를 조회하고 사용자의 요청을 제출하며 명시적인 승인 결정을
처리하고 실행을 취소하므로 `project.read`, `request.dispatch`, `workflow.approve`,
`run.cancel`, `all_projects` 범위를 가진 전용 서비스 계정을 사용한다.

```powershell
uv run jb auth issue `
  --key jarvis-local `
  --name "Jarvis Local Dashboard" `
  --permission project.read `
  --permission request.dispatch `
  --permission workflow.approve `
  --permission run.cancel `
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
Control Plane으로 요청을 proxy한다. 요청 제출은 `jarvis` ingress와 멱등성 key를 사용한다.
실행을 선택하면 노드 상태와 산출물을 조회할 수 있고, 승인 대기 노드는 승인 또는 반려를
한 번 더 확인한 뒤 처리한다. 진행 중인 실행을 취소하려면 화면에 표시된 실행 식별 문구를
정확하게 입력해야 한다. Jarvis는 로컬 실행만 지원하며 외부 네트워크 공개나 Sites 배포는
별도 사용자 인증 계층을 추가하기 전에는 허용하지 않는다.

## Checks

```powershell
npm run format:check
npm run lint
npm test
npm run build
```

계약 테스트는 Control Plane을 실제로 실행하지 않고 server proxy의 인증 header, 오류 전달,
dispatch payload, 멱등 재시도 규칙, 실행 상세·산출물 조회, 승인 결정과 실행 취소 계약을
검증한다. 동일한 검사는 GitHub Actions의 `Jarvis` job에서 모든 `develop` 및 `main` PR과
push에 실행된다.

## System smoke

실제 PostgreSQL, Control Plane, Worker와 Jarvis process 사이의 계약은 저장소 root에서 다음
명령으로 검증한다. 반드시 비어 있는 일회용 test database를 사용해야 한다.

```powershell
$env:JB_ENVIRONMENT = "test"
uv run alembic upgrade head
uv run --with-editable tools/system-smoke-executor jb system smoke
```

smoke executor는 외부 agent runtime을 호출하지 않으며 `JB_ENVIRONMENT=test`가 아니면 시작을
거부한다.
