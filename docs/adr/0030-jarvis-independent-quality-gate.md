# ADR 0030: Jarvis에 독립적인 품질 게이트를 둔다

## 상태

승인됨

## 배경

기존 CI는 Python Control Plane과 Worker만 검사한다. `apps/jarvis`가 추가된 뒤에도 Python
검사만 통과하면 TypeScript compile 오류, server proxy 계약 변경, 멱등 재시도 회귀를 PR에서
발견할 수 없다. 반대로 Jarvis 단위 검사가 실제 PostgreSQL이나 실행 중인 Worker에 의존하면
느리고 불안정해진다.

## 결정

- Jarvis는 자체 `package-lock.json`과 Node 22.13.0을 품질 기준으로 사용한다.
- 모든 `develop` 및 `main` PR과 push에서 `npm ci`를 실행한다.
- format check, lint, contract test, production build를 독립된 `Jarvis` CI job으로 실행한다.
- server proxy 테스트는 browser가 bearer token을 덮어쓸 수 없는지 검증한다.
- dispatch 테스트는 ingress, idempotency key, 정규화된 payload와 upstream 오류를 검증한다.
- 입력 fingerprint와 idempotency key 선택을 순수 함수로 분리해 재시도 규칙을 검증한다.
- 실제 DB·API·Worker를 함께 사용하는 system smoke test는 ADR 0033의 독립 단계로 유지한다.

## 결과

Jarvis 변경은 Python 코드와 독립적으로 빠르게 실패할 수 있고, 전체 CI에서는 두 품질 게이트가
동시에 보호된다. 이번 테스트는 HTTP 계약 경계를 검증하지만 실제 프로세스 배치까지 보장하지
않으므로 통합 실행 smoke test를 대체하지 않는다.
