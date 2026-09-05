# System smoke executor

이 package는 `jb system smoke`에서 Worker process 경계를 검증하기 위한 결정론적 fixture다.
외부 agent runtime을 호출하지 않고 고정된 성공 Artifact를 반환한다. SCM 경계는 실제 GitHub
Publisher와 별도의 loopback API·로컬 bare remote fixture로 검증한다.

일반 Worker 환경에 설치하지 않는다. `JB_ENVIRONMENT=test`가 아니면 factory가 시작을
거부하며 smoke 명령에서만 `uv run --with-editable tools/system-smoke-executor ...`로 임시
설치한다. 전체 smoke는 다음처럼 core, GitHub Publisher와 이 fixture를 함께 설치한다.

```powershell
uv run --with-editable . --with-editable adapters/github --with-editable tools/system-smoke-executor jb system smoke
```
