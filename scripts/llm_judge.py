#!/usr/bin/env python3
"""발행 전 가독성·'AI 느낌' 심사(운영자 지시 2026-11-11). 판단용 모델 1회, 결과는 경고뿐이며 빌드를 막지 않는다.

심사 항목: 스킬 R1.5 일곱 원칙 가운데 기계 검사(easy_check·plain_check)가 못 보는 넷
(정의 전 사용, 결론에 이유, 공시 표현과 다른 풀이, 주장 크기)과 스킬 8.0.2 'AI 느낌'.
출력: 문제 문장 인용 + 이유 + 고칠 방향, 최대 10개. 인용이 원고에 실제로 없는 항목은 버린다.

사용:
  python3 scripts/llm_judge.py content/reports/<slug>.md [--out social/llm/judge/<slug>.md]
  (키가 없거나 크레딧이 없거나 예산을 넘으면 경고 한 줄만 내고 0으로 끝난다)
워크플로: .github/workflows/judge.yml 이 새 리포트 push 때 돌려 social/llm/judge/<slug>.md 를 커밋한다.
미디어 저장소 tools/llm_judge.py 가 이 파일을 불러 쓴다.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402

JUDGE_DIR = llm.ROOT / "social" / "llm" / "judge"
MAX_ITEMS = 10

SYSTEM = """당신은 한국어 주식 리포트의 편집자입니다. 기준 독자는 주식 계좌는 있지만 공시·재무 용어는 모르는 사람입니다.
아래 다섯 가지만 봅니다. 맞춤법, 문장 길이, 화살표·가운뎃점, 표 개수처럼 기계 검사가 이미 보는 것은 보지 않습니다.

1. 정의 전 사용: 뜻을 풀기 전에 쓰인 용어나 우리끼리 붙인 이름(국면 A/B, 시나리오 번호, '판정일', 약어, 표에만 나오는 재무 용어).
2. 결론에 이유 없음: '그래서', '결국', '즉' 같은 판단 앞에 근거 숫자·사실이 없는 문장, 또는 앞 단락과 이어지는 이유 없이 넘어가는 곳.
3. 공시 표현과 다른 풀이: 쉽게 풀면서 실제 조건과 달라진 설명(전환 조건, 대출 한도와 실제 인출액 혼동, 매출과 수주 혼동 등),
   원문에 없는 해석을 덧붙인 곳. 확인할 수 없으면 '원문 확인 필요'로 적습니다.
4. 주장 크기: 작은 표본(8번 중 7번 등)을 '그럴 것이다'로 넓힌 문장, 무엇의 확률인지 밝히지 않은 가능성 숫자, 근거보다 센 단정.
5. AI 느낌: 같은 구조로 시작·끝나는 문단의 반복, '흥미롭게도·주목할 점은·결론적으로·~라는 점입니다' 같은 상투어,
   세 개씩 나열하는 습관, 의미 없는 요약 문장, 번역투('~에 있어서', '~를 통해', '~하는 것이 중요합니다'), 문단 끝 질문 남발.

규칙
- 문제 문장은 원고에서 그대로 복사한 짧은 인용(40자 안팎, 원고에 글자 그대로 있어야 함)으로 줍니다.
- 가장 독자를 멈칫하게 하는 것부터 최대 10개. 문제가 없으면 빈 목록.
- 고칠 방향은 한두 문장으로, 원고에 없는 숫자·사실을 새로 만들지 않습니다.
- 매수·매도 판단이나 종목 전망은 평가하지 않습니다."""

SCHEMA = {"type": "object", "properties": {
    "items": {"type": "array", "items": {"type": "object", "properties": {
        "principle": {"type": "string", "enum": ["정의 전 사용", "결론에 이유", "공시 표현과 다른 풀이", "주장 크기", "AI 느낌"]},
        "quote": {"type": "string"}, "why": {"type": "string"}, "fix": {"type": "string"}},
        "required": ["principle", "quote", "why", "fix"], "additionalProperties": False}},
    "overall": {"type": "string"}}, "required": ["items", "overall"], "additionalProperties": False}


def _squash(s):
    return re.sub(r"\s+", " ", s).strip()


def judge(path):
    """돌려주는 값: (status, markdown 또는 None)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    r = llm.ask("judge", SYSTEM, f"리포트 파일: {p.name}\n\n{text}", tier="judge", max_tokens=8000, effort="medium", schema=SCHEMA)
    if r["status"] != "ok":
        return r["status"], None
    flat = _squash(text)
    items, dropped = [], 0
    for it in (r["json"].get("items") or []):
        q = _squash(it.get("quote", "")).strip("'\"“”‘’ ")
        if len(q) < 4 or q not in flat:
            dropped += 1
            continue
        items.append({**it, "quote": q})
        if len(items) >= MAX_ITEMS:
            break
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# 발행 전 심사: {p.stem}", "",
             f"- 심사 시각: {now} · 경고만(빌드를 막지 않음) · 항목 {len(items)}개" + (f" · 원고에 없는 인용 {dropped}개는 버림" if dropped else ""),
             "- 기준: 스킬 R1.5(정의 전 사용·결론에 이유·공시 표현·주장 크기)와 8.0.2 'AI 느낌'. 고친 뒤 이 파일은 지우지 않아도 된다(다음 push 때 새 리포트만 심사).",
             ""]
    if r["json"].get("overall"):
        lines += [f"> {_squash(r['json']['overall'])}", ""]
    if not items:
        lines.append("지적할 문장 없음.")
    for i, it in enumerate(items, 1):
        lines += [f"{i}. **{it['principle']}** — “{it['quote']}”", f"   - 이유: {_squash(it['why'])}", f"   - 고칠 방향: {_squash(it['fix'])}", ""]
    return "ok", "\n".join(lines).rstrip() + "\n"


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    path = Path(argv[0])
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else JUDGE_DIR / f"{path.stem}.md"
    status, md = judge(path)
    if status != "ok":
        msg = {"no_key": "키 없음(no_key)", "no_credit": "크레딧 없음(no_credit)", "budget": "이번 달 심사 예산 소진"}.get(status, status)
        print(f"::warning::{path.name} 심사 건너뜀 — {msg}. 발행은 막지 않는다.")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"심사 결과: {out} ({md.count(chr(10) + '   - 이유')}개 항목)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
