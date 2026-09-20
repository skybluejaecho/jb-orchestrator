# ADR 0074: 릴리스 준비 상태를 하나의 재현 가능한 게이트로 판정한다

## 상태

채택

## 배경

Python core, Jarvis, OpenClaw protocol contract와 실제 process smoke는 각각 자동 검증되지만,
운영자가 release branch를 만들기 전에 로컬에서 같은 범위를 한 번에 실행할 진입점이 없었다.
또한 GitHub의 개별 job만 보면 일부 job의 실패나 취소를 놓치기 쉬우며 branch protection에 사용할
단일한 최종 판정도 없었다.

## 결정

- `jb system release-check`는 dependency lock, Python 품질과 테스트, Jarvis 품질·테스트·빌드,
  OpenClaw contract를 고정된 순서로 실행하고 첫 실패에서 중단한다.
- 각 단계는 독립 subprocess로 실행하며 단계별 제한 시간을 적용한다. 실패 시 마지막 40줄을
  보존해 어떤 게이트가 왜 실패했는지 바로 확인할 수 있게 한다.
- 기본 검증은 외부 OpenClaw Gateway를 호출하지 않는다. OpenClaw 항목은 pin된 protocol fixture의
  offline contract만 검증한다.
- `--include-system-smoke`는 migration과 실제 process smoke를 추가한다. 이 모드는
  `JB_ENVIRONMENT=test`가 명시되지 않으면 migration 전에 실패해 운영 database 오용을 막는다.
- GitHub Actions의 `Release readiness` job은 모든 독립 job의 결과를 모아 하나라도 성공하지
  못하면 실패한다. 개별 job의 병렬성과 진단 로그는 그대로 유지한다.
- release-check는 작업 트리의 청결 여부나 branch 이름을 강제하지 않는다. 개발 중에도 동일한
  게이트를 실행할 수 있어야 하며, Git flow 적용과 merge 승인은 별도의 사람 중심 절차다.

## 결과

- 로컬과 CI에서 릴리스 후보가 통과해야 할 경계가 명시적으로 드러난다.
- 전체 smoke는 사용자가 disposable PostgreSQL을 준비했을 때만 선택적으로 실행된다.
- 새로운 배포 표면을 추가할 때 로컬 단계와 CI 최종 집계 모두 갱신해야 한다.
- 실제 OpenClaw Gateway 연결과 provider credential 검증은 환경별 acceptance로 남으며 이 판정이
  production 연결 준비를 과장하지 않는다.
