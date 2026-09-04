# Jarvis local dashboard

Jarvis는 jb-orchestrator의 진실의 원천이 아니라 로컬 관찰 UI다. 프로젝트, 요청 및
Workflow 상태를 Control Plane API에서 읽고 프로젝트 SSE stream으로 변경을 감지한다.

## Local setup

Jarvis는 프로젝트 상태를 조회하고 사용자의 요청을 제출하므로 `project.read`,
`request.dispatch`, `all_projects` 범위를 가진 전용 서비스 계정을 사용한다.

```powershell
uv run jb auth issue `
  --key jarvis-local `
  --name "Jarvis Local Dashboard" `
  --permission project.read `
  --permission request.dispatch `
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
승인이나 취소 기능은 아직 제공하지 않으며 로컬 실행만 지원한다. 외부 네트워크 공개나
Sites 배포는 별도 사용자 인증 계층을 추가하기 전에는 허용하지 않는다.

## Checks

```powershell
npm run lint
npm run build
```
