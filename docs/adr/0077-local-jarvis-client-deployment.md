# ADR 0077: Jarvis는 서버와 분리된 로컬 클라이언트로 배포한다

## 상태

채택

## 배경

ORCH-079의 단일 host 구성은 첫 운영 배치를 재현했지만 Jarvis도 서버의 Compose profile로
포함했다. 현재 Jarvis에는 별도 사용자 로그인 계층이 없고 강한 service-account token을
server route가 보관한다. Jarvis port를 원격 서버에 게시하면 UI 접근 가능 범위와 Control Plane
권한이 불필요하게 함께 넓어진다. 향후 Flutter나 다른 클라이언트도 동일한 Control Plane 계약에
연결하려면 UI를 서버 process의 필수 구성으로 취급해서는 안 된다.

## 결정

- 저장소는 monorepo로 유지하지만 배포 구성을 server와 client로 분리한다.
- server 구성에는 PostgreSQL, migration, Control Plane, readiness monitor와 선택적 Worker만
  포함하며 Jarvis service와 Jarvis credential을 포함하지 않는다.
- server API host port는 기본적으로 loopback에만 게시한다. SSH tunnel을 사용하지 않는 운영자는
  명시적으로 VPN interface 또는 별도 HTTPS reverse proxy가 소유하는 interface를 선택해야 한다.
- Jarvis는 신뢰된 사용자 workstation의 독립 Compose project로 실행한다.
- Jarvis host port는 `127.0.0.1`에 고정하여 workstation 외부에서 UI에 접근하지 못하게 한다.
- 각 Jarvis 설치는 원격 Control Plane URL과 해당 설치에만 발급된 최소 권한 service-account
  token을 사용한다. Browser에는 token을 전달하지 않는 기존 server proxy 경계를 유지한다.
- Jarvis client는 server Compose service 이름이나 Docker network에 의존하지 않는다.
- CI와 source-level 계약 테스트는 두 Compose 파일을 각각 검증한다.

## 결과

- 원격 서버는 UI를 공개하지 않고 orchestration과 Worker 실행만 소유한다.
- 사용자는 로컬 브라우저로 자신의 Jarvis container에 접속한다.
- SSH tunnel이나 사설 VPN 환경에서 공인 domain 없이도 배포할 수 있다.
- Jarvis와 향후 Flutter client는 PostgreSQL에 직접 접근하지 않고 동일한 Control Plane API와
  SSE 원장을 사용한다.
- 이미지 registry, 기기 token 수명주기, 일회용 pairing, 생성형 client SDK는 후속 결정으로 남긴다.
