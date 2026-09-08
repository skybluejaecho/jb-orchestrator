# 컨테이너 이미지 릴리스

Runtime과 Jarvis는 하나의 제품 버전으로 함께 검증하지만 서로 다른 GHCR package로 발행한다.

- `ghcr.io/skybluejaecho/jb-orchestrator-runtime:<version>`
- `ghcr.io/skybluejaecho/jb-orchestrator-jarvis:<version>`

운영 환경에서는 `latest` 대신 `0.1.0`처럼 정확한 버전을 사용한다. `sha-<commit>` tag는 배포
원본을 추적하거나 사고 대응 시 특정 commit으로 고정할 때 사용할 수 있다.

## 릴리스 준비

1. `develop`에서 `release/<version>` branch를 만든다.
2. `pyproject.toml`의 project version과 `apps/jarvis/package.json`의 version을 같은 안정
   SemVer로 변경한다.
3. dependency 변경이 포함됐다면 Runtime 잠금 export를 갱신한다.

~~~powershell
$env:UV_CACHE_DIR='.uv-cache'
uv export --frozen --no-dev --no-emit-project --format requirements-txt `
  --output-file deploy/server/requirements.lock
~~~

4. 아래 검사를 실행하고 release branch를 `main`에 review를 거쳐 병합한다.

~~~powershell
uv run python tools/release/verify_version.py v0.1.0
uv run jb system release-check --include-system-smoke
~~~

5. 병합된 `main` commit에 서명된 annotated tag를 만들고 push한다.

~~~powershell
git tag -s v0.1.0 -m "v0.1.0"
git push origin v0.1.0
~~~

6. Git Flow 이력을 닫기 위해 release branch의 version commit을 `develop`에도 병합하고, 다음 개발
   주기를 시작할 때 Runtime과 Jarvis version을 함께 다음 development version으로 변경한다.

`Container image release` workflow는 tag가 안정 SemVer인지, 두 component version과 같은지,
tag commit이 `main`에 포함됐는지 확인한 뒤에만 두 package를 push한다. 발행에는 repository의
`GITHUB_TOKEN`과 `packages: write` 권한만 사용하며 별도 장기 PAT를 workflow에 저장하지 않는다.

서명용 GPG key가 준비되지 않은 초기 환경에서는 tag 서명 정책을 먼저 정한 뒤 진행한다. 서명을
생략해야 한다면 그 이유를 release 기록에 남기되 workflow의 version 및 main-history 검증은
우회하지 않는다.

## 최초 GHCR 설정

첫 발행 후 GitHub package 설정에서 repository 연결과 visibility를 확인한다. Package가 private이면
각 Docker host에 package read 권한만 가진 credential을 저장하고 `docker login ghcr.io`를 먼저
실행한다. Public으로 전환하더라도 Control Plane port와 service-account token 정책은 달라지지
않는다.

## 서버와 클라이언트 갱신

서버의 `deploy/server/.env`에는 Runtime version만 고정한다.

~~~dotenv
JB_RUNTIME_IMAGE=ghcr.io/skybluejaecho/jb-orchestrator-runtime:0.1.0
~~~

사용자 PC의 `deploy/clients/jarvis/.env`에는 같은 release의 Jarvis version을 고정한다.

~~~dotenv
JB_JARVIS_IMAGE=ghcr.io/skybluejaecho/jb-orchestrator-jarvis:0.1.0
~~~

각 host에서 해당 Compose 파일에 대해 `pull` 후 `up -d`를 실행한다. 서버와 Jarvis는 별도
Compose project이므로 점검 후 서로 다른 시점에 갱신할 수 있다. 문제가 있으면 환경 파일의 image
tag를 이전 안정 버전으로 되돌리고 같은 명령을 다시 실행한다. PostgreSQL volume이나 OpenClaw
device volume은 image rollback 과정에서 삭제하지 않는다.
