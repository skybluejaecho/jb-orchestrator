# ADR 0019: 프로젝트 Workflow 바인딩으로 요청을 원자적으로 디스패치한다

## 상태

승인됨

## 배경

기존 API에서는 사용자가 요청을 만든 뒤 생성된 Run ID와 실행할 Workflow의 key/version을
별도로 전달해야 했다. 이 방식은 관리자용 제어에는 유용하지만 Jarvis, OpenClaw 같은
최종 사용자 채널이 Workflow 선택 정책을 알아야 하고 두 호출 사이에 실패할 수 있다.

또한 “현재 이 프로젝트가 어떤 흐름을 사용하는가”라는 설정과 실제 실행에서 사용한 정의가
PostgreSQL에 함께 남아야 실행 재현성과 조회 정합성을 보장할 수 있다.

## 결정

- 프로젝트마다 현재 사용할 Workflow 정의를 하나 연결한다.
- 바인딩은 `latest` 별칭이 아니라 정의의 ID, key, version을 모두 저장한다.
- 바인딩 생성과 변경 시 프로젝트와 정확한 Workflow 버전의 존재를 검증한다.
- 바인딩 변경은 이후 요청에만 적용한다.
- 단일 dispatch 유스케이스가 User Request, Run, Workflow Execution과 관련 이벤트를 한
  트랜잭션에서 생성한다.
- dispatch는 바인딩 row를 잠근 뒤 정확한 정의를 다시 확인한다.
- 실행 스냅샷에는 정의와 프로젝트·사용자 요청 문맥을 기존과 동일하게 고정한다.
- `workflow.started` 이벤트의 `selection_source`로 `project_binding` 또는 `explicit`을 남긴다.
- 기존 수동 요청 생성 및 Workflow 시작 API는 운영·테스트·재실행 도구를 위해 유지한다.

## 사용자 흐름

```text
관리자: Workflow v1 등록 ─> 프로젝트에 v1 연결
                                   │
사용자/Jarvis/OpenClaw: 요청 1회 ──┤
                                   v
                    Request + Run + Execution + Events
                                   │  단일 DB transaction
                                   v
                     Worker들이 READY 노드를 실행

관리자: 프로젝트를 Workflow v2로 변경
       ├─ 기존 Execution: v1 snapshot 유지
       └─ 다음 dispatch:  v2 snapshot 생성
```

## 결과

클라이언트는 사용자 문장을 전달하는 역할에 집중하고 Workflow 선택은 서버 설정으로
통제한다. 요청 접수 후 실행 누락이 생기지 않으며, 현재 설정과 과거 실행 결정을 모두
PostgreSQL에서 설명할 수 있다.

요청 내용에 따른 동적 Workflow 선택, 여러 후보의 정책 기반 라우팅, 사용자별 override는
프로젝트 기본 바인딩 위에 별도의 선택 정책으로 확장한다.
