# ADR 0015: 노드 사이 문맥은 Snapshot과 Artifact로 전달한다

## 상태

승인됨

## 배경

서로 다른 에이전트 세션에 전체 대화 기록을 전달하면 불필요한 지시와 중간 추론이 섞이고,
세션이 사라졌을 때 다음 단계를 재현하기 어렵다. 반대로 노드 지시문만 전달하면 에이전트가
원본 사용자 요청과 앞 단계의 결과를 알 수 없다.

## 결정

- Workflow 시작 시 사용자 요청과 프로젝트·저장소 식별 정보를 Snapshot에 복사한다.
- Task 노드가 완료될 때마다 `(execution, producer node, visit count)`로 식별되는 불변 JSON
  Artifact를 같은 트랜잭션에서 저장한다.
- 다음 Task Claim에는 현재 노드로 직접 연결되는 선행 노드별 최신 Artifact만 전달한다.
- 원본 요청, 프로젝트 정보, 직접 선행 Artifact, 검증된 Skill 경로를 Executor가 받는
  `TaskContextEnvelope`로 구성한다.
- 기존 Snapshot에는 요청 컨텍스트가 없을 수 있으므로 역직렬화와 Executor 계약은 하위
  호환을 유지한다.
- 전체 Artifact 이력은 API에서 조회할 수 있다.

## 흐름

```text
UserRequest + Project
        │
        └── Workflow Snapshot에 고정

Planning node ── TaskArtifact(plan, visit=1) ──┐
                                               ├─> Implementation TaskContext
Review node ─── TaskArtifact(review, visit=2) ─┘
```

Task 재시도는 같은 방문의 Artifact를 생성하지 않는다. Task가 비즈니스 결과를 반환하고
완료된 경우에만 Artifact가 생성된다. 루프가 다시 노드를 방문하면 새로운 `visit_count`로
기존 결과를 덮어쓰지 않고 추가한다.

## 결과

각 에이전트는 새로운 세션에서도 필요한 사실만 받아 실행할 수 있고, 단계 간 전달 내용은
PostgreSQL에서 재현할 수 있다. 현재 Artifact는 JSON 문서에 한정한다. 큰 파일이나 바이너리
산출물은 후속 Artifact 저장소가 URI와 digest를 저장하는 방식으로 확장한다. Phase Pack의
명시적 입출력 매핑이 추가되기 전까지는 직접 선행 노드의 최신 Artifact가 기본 입력이다.
