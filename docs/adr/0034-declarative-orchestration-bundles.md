# ADR 0034: 오케스트레이션 구성을 선언형 Bundle로 적용한다

## 상태

승인됨

## 배경

Skill, Model Profile, Phase Pack, Workflow와 Project Binding은 이미 Control Plane의 버전 고정
리소스다. 그러나 각각을 raw HTTP 요청으로 등록하면 적용 순서를 사람이 기억해야 하고, 여러
개발자가 같은 구성을 재현하거나 변경 내용을 리뷰하기 어렵다. Jarvis가 독자적인 구성 저장소를
가지면 PostgreSQL과 UI 상태 사이에 두 번째 진실의 원천도 생긴다.

## 결정

- YAML `schema_version: 1` Bundle은 선택적인 Project 하나와 Skill, Model Profile, Phase Pack,
  Workflow 목록 및 선택적인 Project Binding을 표현한다.
- `jb bundle validate`는 네트워크 없이 Pydantic 스키마, JSON Schema 출력 계약, Workflow 그래프,
  포함된 Phase Pack의 입력 매핑을 검증한다.
- Bundle에 포함되지 않은 정확한 Skill, Phase Pack 또는 Workflow 참조는 외부 의존성으로
  명시한다. `plan`은 Control Plane에서 해당 버전이 실제로 존재하는지 확인한다.
- `jb bundle plan`은 현재 API 상태를 읽어 `create`, `update`, `unchanged`, `conflict` 작업을
  출력하며 상태를 변경하지 않는다.
- Project와 버전 고정 catalog identity가 다른 내용으로 이미 존재하면 conflict로 처리한다.
  `apply`는 하나라도 conflict가 있으면 쓰기를 시작하지 않는다.
- `jb bundle apply`는 Project, Skill, Model Profile, Phase Pack, Workflow, Binding 순으로 기존
  Control Plane API를 호출한다. CLI가 application 규칙이나 DB 쓰기를 복제하지 않는다.
- Bundle 파일은 secret이나 bearer token을 포함하지 않는다. 인증은 기존 `JB_API_TOKEN` 환경
  설정을 사용한다.

## 결과

구성을 Git에서 리뷰하고 여러 환경에 반복 적용할 수 있으며, 이후 Jarvis 구성 UI도 동일한
Control Plane 리소스를 다룰 수 있다. 여러 HTTP 요청을 하나의 분산 transaction으로 만들지는
않으므로, 네트워크 실패 후 같은 Bundle을 다시 plan/apply하여 수렴한다. 기존 immutable identity는
덮어쓰지 않으며 변경된 내용은 새 version으로 등록해야 한다.
