# llm-tasks — 다른 세션이 `llm-task.yml`에 넘기는 프롬프트

- 파일 하나 = 작업 하나: `llm-tasks/<task>.md`(프롬프트, 40,000자 이하), 선택 `llm-tasks/<task>.schema.json`(JSON 스키마, 모든 object에 `"additionalProperties": false`).
- 비밀값(키·토큰·비밀번호)·개인정보(실명·이메일·전화·주민번호)·공개 전 민감한 숫자는 넣지 않는다. 걸리면 워크플로가 보내지 않고 `refused`로 남긴다.
- 다 쓴 프롬프트 파일은 지워도 된다(결과는 `social/llm/tasks/<task>-<run_id>.json`에 남는다).
- 전체 사용법: `docs/LLM_ACCESS.md`.
