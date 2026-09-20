# ADR 0052: 실패한 SCM 게시는 같은 원장에서 명시적으로 재시도한다

## 상태

승인됨

## 배경

SCM Worker는 provider 오류를 안전하게 실패로 기록하지만 일시적인 네트워크 문제나 서비스 장애도
terminal 실패가 된다. 새 게시 요청을 만들면 원래 요청과 attempt 이력이 분리되고, 자동 무제한
재시도는 잘못된 인증이나 Git 상태에서 외부 호출을 반복할 위험이 있다.

## 결정

- `ScmPublication.attempt_count`를 추가하고 Worker가 claim할 때마다 증가시킨다.
- `POST /v1/scm-publications/{id}/retry`는 failed 레코드만 같은 ID로 pending 상태에 되돌린다.
- pending 또는 claimed 레코드에 대한 반복 호출은 현재 레코드를 재사용하고 succeeded 레코드는
  거부한다.
- 재시도 전에 external execution의 worktree가 release되지 않았고 source branch가 게시 요청과
  여전히 같은지 확인한다.
- retry는 이전 worker, lease, result, failure와 completed 시각을 비우되 attempt count와 원래
  게시 입력은 보존한다.
- `scm_publication.retried` 이벤트에 수행 계정과 누적 attempt를 남긴다.
- publication ID 기반 권한 검사는 external execution과 run을 거쳐 project scope를 해석한다.
- Jarvis는 failed이면서 아직 사용 가능한 worktree에만 재시도 버튼을 표시한다.
- 자동 backoff나 무제한 provider 재호출은 이 단계에 포함하지 않는다.

## 결과

사용자는 한 게시 의도와 감사 이력을 유지한 채 일시적 실패를 복구할 수 있다. Worker crash는 기존
lease 만료 회수가 담당하고, provider 실패의 재실행은 계속 명시적인 사용자 결정으로 남는다.
