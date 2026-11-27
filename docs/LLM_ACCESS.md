# API 크레딧 쓰는 법 — 다른 세션·다른 팀용 (운영자 지시 2026-11-27 "다 옮겨. 다른 세션에서도 좀 쓰게 접근 지침 작성해")

이 문서 하나만 읽고 어느 세션(김박사 월드 제작, healthworld, 다른 팀)이든 Anthropic API 크레딧을 쓸 수 있게 쓴 것이다.
미디어 저장소가 있으면 같은 내용이 `skill/runbooks/api.md`에도 있다.

## 0. 한 줄 요약
키는 세션에 없다. **사이트 저장소 `phdkimworld/kimworld-site`의 워크플로를 실행 요청**하면 GitHub Actions가 키로 모델을 부르고, 결과를 저장소 파일로 커밋한다. 세션은 그 파일에서 필요한 필드만 읽는다.

## 1. 준비
1. 세션에 GitHub MCP 도구(`actions_run_trigger`, `get_file_contents`)가 있어야 한다.
2. 저장소가 세션에 없으면 `mcp__claude-code-remote__add_repo` 를 `{"owner": "phdkimworld", "repo": "kimworld-site", "access": "push"}` 로 부른다(워크플로 실행과 `llm-tasks/` 커밋에 쓰기 권한 필요). 미리 curl·`gh repo view`로 확인하지 말고 바로 부른다. 거절되면 도구가 준 사유를 그대로 운영자에게 전한다.
3. 복제는 선택이다. 결과는 `get_file_contents`로 파일 하나만 읽어도 된다. 복제했다면 `git pull --rebase origin main`.
4. 키·토큰 값은 어디에도 출력하지 않는다. 세션에 `ANTHROPIC_API_KEY`가 없는 것이 정상이다.

## 2. 쓸 수 있는 워크플로 (ref 는 언제나 `main`)
| 워크플로 | 하는 일 | 입력 | 결과 파일 | 예산(월) |
|---|---|---|---|---|
| `llm-task.yml` | **범용(다른 세션 몫)**: 프롬프트 하나 → 답(글 또는 JSON 스키마) | `task`, `prompt`(≤4,000자) 또는 `prompt_path`(`llm-tasks/` 아래), 선택 `schema_path`·`max_tokens`(≤4000)·`caller` | `social/llm/tasks/<task>-<run_id>.json` | shared 20달러 |
| `extract.yml` | 공시·IR 페이지 → 정해진 숫자 표(JSON) | `slug`, `urls`(https, 쉼표, ≤6, PDF 안 됨), `preset`(filing), 선택 `focus` | `social/llm/extract/<slug>.json` | extract 15달러 |
| `sns-draft.yml` | 리포트 → Threads th1/th2(+관찰 글)·릴스 캡션 초안 + 규칙 검사 | `slug`, 선택 `facts`·`observe` | `social/llm/sns/<slug>.json` | sns 10달러 |
| `blogger-draft.yml` | 리포트 → 블로거 머리말 `blog_slug`·`blog_intro`·`blog_faq` 초안 + 검사 | `slug` | `social/llm/blogger/<slug>.md` | blogger 5달러 |
| `judge.yml`, `comment-ai.yml`, `weekly-ai.yml` | 김박사 월드 제작 전용(발행 전 심사·댓글 답글·주간 분석) | — | — | — |

모든 워크플로에 `dry: "1"` 입력이 있다: 모의 응답으로 끝까지 돌고 커밋하지 않는다(크레딧 0, 입력 형식 확인용).

## 3. 실행 요청 예시 (MCP `actions_run_trigger`, method `run_workflow`)
짧은 프롬프트:
```json
{"method": "run_workflow", "owner": "phdkimworld", "repo": "kimworld-site", "ref": "main",
 "workflow_id": "llm-task.yml",
 "inputs": {"task": "hw-faq-tone", "prompt": "다음 세 문장을 50대 독자가 읽기 쉬운 존댓말로 고쳐 줘: ...", "max_tokens": "800", "caller": "healthworld"}}
```
긴 프롬프트·JSON 답: 먼저 `llm-tasks/hw-labels.md`(프롬프트)와 `llm-tasks/hw-labels.schema.json`(모든 object에 `"additionalProperties": false`)을 main에 커밋하고
```json
{"method": "run_workflow", "owner": "phdkimworld", "repo": "kimworld-site", "ref": "main",
 "workflow_id": "llm-task.yml",
 "inputs": {"task": "hw-labels", "prompt_path": "llm-tasks/hw-labels.md", "schema_path": "llm-tasks/hw-labels.schema.json", "max_tokens": "2000", "caller": "healthworld"}}
```
공시 표 뽑기:
```json
{"method": "run_workflow", "owner": "phdkimworld", "repo": "kimworld-site", "ref": "main",
 "workflow_id": "extract.yml",
 "inputs": {"slug": "plug-2026-11-6", "urls": "https://www.sec.gov/Archives/edgar/data/<CIK>/<접수번호>/<문서>.htm,https://<IR 보도자료 주소>", "preset": "filing"}}
```
SNS·블로거 초안: `{"workflow_id": "sns-draft.yml", "inputs": {"slug": "<리포트 slug>", "observe": "1"}}`, `{"workflow_id": "blogger-draft.yml", "inputs": {"slug": "<리포트 slug>"}}` (나머지 키는 위와 같다).
`gh`가 있는 세션: `gh api -X POST repos/phdkimworld/kimworld-site/actions/workflows/llm-task.yml/dispatches -f ref=main -f 'inputs[task]=hw-faq-tone' -f 'inputs[prompt]=...'`

## 4. 결과 받기 — 필요한 필드만
- 실행은 보통 1~3분. 실행 ID는 `actions_list`(`list_workflow_runs`, resource_id `llm-task.yml`, perPage 3)로 본다. 결과 파일 이름의 `<run_id>`가 그 실행 ID다.
- 기다릴 때는 짧은 간격으로 계속 확인하지 말고 3분 뒤 한 번(세션 규칙: 긴 대기는 send_later 하나).
- 읽기(복제본): `git pull -q --rebase origin main` 후
  - 범용: `jq -r '.status, .error, .text' social/llm/tasks/hw-faq-tone-<run_id>.json` / JSON 답이면 `jq '.json'`
  - 표: `jq -r '.rows[] | [.date, .form, .item, .amount, .unit, .shares, .price, .quote_found] | @tsv' social/llm/extract/<slug>.json`
  - SNS: `jq '.status, .problems' social/llm/sns/<slug>.json`, 파일 하나 꺼내기 `jq '.files["<slug>-th2.json"]' social/llm/sns/<slug>.json > social/queue/<slug>-th2.json`
  - 블로거: `sed -n '/```yaml/,/```/p' social/llm/blogger/<slug>.md`
- 복제본이 없으면 `get_file_contents`(owner phdkimworld, repo kimworld-site, path 위 경로)로 그 파일 하나만.
- `status` 값: `ok` · `ok_with_problems`(초안은 있으나 규칙 검사 지적이 남음, `problems` 참고) · `no_key`/`no_credit`/`budget`/`bad_key`(건너뜀 — 세션이 예전 방식으로 처리) · `daily_cap`/`run_cap`(하루·실행 상한) · `refused`(비밀값·개인정보 모양) · `truncated`(max_tokens 부족) · `refusal` · `error`.

## 5. 예산·상한 확인
- 월 예산(사이트 `scripts/llm.py` BUDGETS): comments 40 · judge 25 · weekly 10 · extract 15 · sns 10 · blogger 5 · **shared 20** 달러, 전체 상한 120달러(기능별 합이 넘어도 120에서 모두 멈춤). 사이트 Q&A 몫은 따로.
- 하루 호출 상한: extract 10 · sns 8 · blogger 8 · **shared 20(모든 세션 합)**. 실행당 extract 1 · sns 2 · blogger 2 · task 1회.
- 현황: 복제본에서 `python3 scripts/llm.py status`(키 없음으로 나오는 것이 정상, 금액은 장부 `social/llm/usage.json` 기준). 오늘 쓴 횟수: `ls social/llm/runs/$(date -u +%F)/`.

## 6. 보내면 안 되는 것
- 비밀값: API 키·토큰·비밀번호·OAuth 값·개인 키. 워크플로가 모양을 찾으면 보내지 않고 `refused`(무엇이 걸렸는지 이름만 남김).
- 개인정보: 실명·이메일·전화·주소·주민번호, 환자·고객 기록, 운영자 신상과 종목 보유 여부.
- 공개 전 민감한 숫자(발표 전 실적·내부 계약 조건 등)와 남의 유료 리포트 원문. 결과 파일은 저장소에 커밋되어 남는다는 점을 기억한다.
- 모델 답은 초안이다. 숫자·사실의 최종 판단, 대본·리포트 본문 집필, 투자 판단은 맡기지 않는다. 표 뽑기 결과도 핵심 숫자 2~3개는 원문에서 직접 확인한다.

## 7. 비용 예절 (shared 20달러/월을 여러 세션이 나눠 씀)
- 작은 질문 여러 개는 한 프롬프트로 묶어 한 번에 보낸다(하루 20회는 모든 세션 합).
- 긴 자료는 필요한 부분만 잘라 `llm-tasks/`에 커밋한다. 같은 요청을 되풀이하지 않는다(결과 파일을 다시 읽는다).
- `max_tokens`는 필요한 만큼만(기본 1500). JSON이 필요하면 스키마를 줘서 다시 묻는 일을 줄인다.
- 처음 쓰는 형식은 `dry: "1"`로 입력부터 확인한다.
- 예산이 모자라면 예산 숫자를 고치지 말고 운영자에게 보고한다(숫자는 운영자 지시로만 바꾼다).
