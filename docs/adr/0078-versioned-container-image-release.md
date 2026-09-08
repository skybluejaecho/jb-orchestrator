# ADR 0078: Runtime과 Jarvis 이미지는 동일한 안정 버전으로 발행한다

## 상태

채택

## 배경

ORCH-080은 원격 server와 로컬 Jarvis client의 실행 구성을 분리했지만 두 host 모두 source
checkout에서 이미지를 직접 build해야 했다. 이 방식은 배포 host마다 build 결과와 toolchain이
달라질 수 있고, 어떤 source revision이 실행 중인지 명확히 증명하기 어렵다. 반대로 이동하는
`latest` tag를 자동 배포하면 server와 client가 서로 다른 시점에 갱신되어 API 계약이 어긋날 수
있다.

## 결정

- Runtime과 Jarvis를 각각 `ghcr.io/<owner>/jb-orchestrator-runtime` 및
  `ghcr.io/<owner>/jb-orchestrator-jarvis` package로 발행한다.
- 모든 pull request와 `develop`/`main` push에서 두 Dockerfile을 실제 build하고 non-root user 및
  기본 entry point를 검증한다. 이 결과를 통합 Release readiness gate에 포함한다.
- image 발행은 `main` history에 포함된 commit의 안정 SemVer tag `vX.Y.Z`에만 허용한다.
- tag version은 Python project와 Jarvis package version 모두와 정확히 같아야 한다.
- 같은 release에서 두 image에 동일한 SemVer tag와 `sha-<commit>` tag를 부여한다.
- `latest`, branch name 등 이동하는 tag는 발행하지 않는다.
- Runtime third-party Python dependency는 `uv.lock`에서 생성한 hash-locked export로 설치하고
  CI에서 두 파일의 동기화를 검사한다. Jarvis dependency는 package lock을 사용한다.
- image에는 OCI source metadata, 최대 provenance, SBOM을 포함한다.
- server와 Jarvis의 Compose project는 각자 환경 파일에서 배포할 정확한 version을 고정한다.

## 결과

- 서로 다른 host에서도 동일 source와 version의 image를 재사용할 수 있다.
- server와 client는 독립적으로 갱신하면서도 호환 version을 명시적으로 선택한다.
- release branch에서 두 component version을 함께 변경하지 않으면 발행이 실패한다.
- 첫 GHCR 발행 후 package 공개 범위와 pull credential은 운영자가 repository 정책에 맞게
  설정해야 한다.
- image 서명, 취약점 정책 gate, 다중 architecture 발행은 실제 배포 요구를 확인한 뒤 별도
  결정한다.
