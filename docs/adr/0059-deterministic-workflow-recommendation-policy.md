# ADR 0059: Workflow 추천은 버전 고정 후보를 설명하는 결정적 정책으로 시작한다

## 배경

요청별 Workflow 선택과 구성 미리보기는 이미 지원하지만, 사용자는 등록된 Workflow가 많아질수록
어떤 구성을 골라야 하는지 직접 판단해야 한다. 자유 문장을 곧바로 LLM에 맡겨 자동 실행하면 같은
요청의 선택이 달라질 수 있고, 낮은 확신의 판단이 비용이나 부작용이 큰 Workflow를 시작할 수 있다.

## 결정

- 추천 정책은 요청의 정규화된 용어와 planning, implementation, verification, repair, research
  의도를 Workflow key, 노드 지시문, Phase Pack과 Skill 설명에 비교한다.
- 후보는 점수, 일치 용어, 일치 의도, 프로젝트 기본값 여부와 정확한 `key@version`을 반환한다.
- 점수, 동점 해소와 신뢰도 임계값은 `workflow-keyword-v1` 정책 버전에 고정한다.
- 높은 신뢰도만 추천 결과를 직접 사용할 수 있다. 중간 또는 낮은 신뢰도는 정확한 후보를 명시적으로
  확인해야 한다.
- 추천 요청은 prompt 원문 대신 SHA-256 digest, 정책 버전, 후보와 근거를 프로젝트 이벤트로
  저장한다. 반환한 이벤트 UUID가 recommendation ID다.
- Dispatch는 recommendation ID의 프로젝트, prompt digest와 선택 후보를 다시 검증한다.
- 추천이 없는 기존 프로젝트 binding과 request override 흐름은 그대로 유지한다.
- Jarvis는 추천 후보를 보여주고 사용자가 후보를 바꿀 수 있게 하며, 브라우저가 최종 정책 판단의
  진실의 원천이 되지 않는다.

## 결과

사용자는 요청에 맞는 Workflow를 빠르게 찾으면서도 최종 실행 버전과 판단 근거를 PostgreSQL
이벤트에서 추적할 수 있다. 향후 embedding이나 LLM classifier를 추가하더라도 같은 후보 제한,
신뢰도, 확인, recommendation ID 계약 뒤의 새로운 정책 버전으로 교체할 수 있다.
