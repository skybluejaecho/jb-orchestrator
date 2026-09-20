# ADR 0060: Worker 배정 경보는 READY 발생 단위의 원장으로 관리한다

## 배경

프로젝트 배정 진단은 현재 시점에 처리 가능한 Worker가 없는 이유를 설명하지만, 같은 문제를
반복 조회할 때마다 새로운 경고로 취급하거나 언제 시작되고 해소됐는지 추적할 수 없다. Jarvis
브라우저 메모리로 지속 시간을 관리하면 화면이 닫힌 동안의 상태와 다른 클라이언트의 판단이
달라진다.

## 결정

- 경보 발생 단위는 Workflow Execution, node key와 해당 노드의 `ready_since` 조합이다.
- 원장은 active와 resolved 상태, 최초 감지, 마지막 관찰, 해소 시각과 진단 reason을 보존한다.
- 프로젝트 평가가 같은 발생 단위를 다시 발견하면 기존 경보의 마지막 관찰 시각만 갱신한다.
- 더 이상 현재 진단에 없는 active 경보는 삭제하지 않고 resolved로 전환한다.
- 경보 생성, reason 변경과 해소는 프로젝트 이벤트로 기록해 SSE 소비자가 갱신할 수 있게 한다.
- API가 설정된 지속 임계값을 기준으로 warning과 critical을 계산하고, reason에 따라
  `start_capable_worker` 또는 `restart_capable_worker` 조치를 제공한다.
- 진단 GET은 현재 상태와 기존 원장을 읽기만 한다. 명시적인 evaluate POST가 경보 원장을
  조정하며 `project.read` 범위 안에서 안전한 파생 상태 갱신으로 취급한다.
- Jarvis는 30초마다 evaluate를 호출하지만 경보 식별과 수명은 PostgreSQL이 소유한다.

## 결과

브라우저를 닫거나 다른 입력 주체가 평가해도 동일한 경보 ID와 지속 시간을 관찰할 수 있다.
향후 알림 어댑터는 active/critical 이벤트만 전달하고 alert ID로 중복 전송을 억제할 수 있다.
Worker 프로세스를 자동 시작하는 기능은 이 경보 원장과 별개의 승인 기반 제어 기능으로 남긴다.
