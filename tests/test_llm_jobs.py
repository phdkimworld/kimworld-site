"""scripts/llm_jobs.py·sns_rules.py 검사(네트워크·키 없이, 모의 응답). python3 tests/test_llm_jobs.py"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
tmp = Path(tempfile.mkdtemp())
os.environ["LLM_USAGE_FILE"] = str(tmp / "usage.json")
os.environ["LLM_DELTA_FILE"] = str(tmp / "delta.json")
os.environ["LLM_JOBS_OUT"] = str(tmp / "out")
os.environ["CHANGED_FILE"] = str(tmp / "changed.txt")
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("LLM_MOCK_RESPONSE", None)
os.environ.pop("GITHUB_RUN_ID", None)
import llm  # noqa: E402
import llm_jobs as J  # noqa: E402
import sns_rules as R  # noqa: E402

ok = 0


def check(name, cond):
    global ok
    if not cond:
        print("FAIL", name)
        sys.exit(1)
    ok += 1
    print("  ok ", name)


class A:  # argparse 대신
    def __init__(self, **kw):
        self.__dict__.update(dict(mock=False, no_write=False, slug="", urls="", preset="filing", focus="", facts="", observe=False,
                                  task="", prompt_path="", prompt="", schema_path="", max_tokens="1500", caller=""), **kw)


# 예산
check("새 예산 넷", llm.budget("extract") == 15 and llm.budget("sns") == 10 and llm.budget("blogger") == 5 and llm.budget("shared") == 20)
check("전체 상한 그대로 120", llm.total_cap() == 120)
buf = io.StringIO()
with redirect_stdout(buf):
    llm.status()
check("status 에 새 기능", all(f"{k}:" in buf.getvalue() for k in ("extract", "sns", "blogger", "shared")))

# 비밀값·개인정보
fake = "sk-ant-" + "a1" * 10
check("Anthropic 키 모양 걸림", "Anthropic 키" in J.secret_hits(f"키는 {fake} 입니다"))
check("GitHub 토큰 걸림", J.secret_hits("ghp_" + "x" * 30))
check("주민번호·휴대폰·이메일 걸림", {"주민등록번호", "휴대폰 번호", "이메일 주소"} <= set(J.secret_hits("900101-1234567 010-1234-5678 a.b@ex.com")))
check("평범한 글은 통과", J.secret_hits("PLUG 11월 25일 종가 1.065달러, 하루 +14.3%") == [])
check("결과의 키 모양은 가림", "[가림]" in J.redact({"t": [f"x {fake}"]})["t"][0])

# 주소·HTML
check("https만", J.url_problem("http://sec.gov/x") and not J.url_problem("https://www.sec.gov/Archives/x.htm"))
check("IP·내부 주소 금지", J.url_problem("https://127.0.0.1/a") and J.url_problem("https://localhost/a") and J.url_problem("https://u:p@ex.com/"))
t = J.html_to_text("<html><head><title>x</title></head><body><script>bad()</script><p>Net loss&nbsp;was $1,234</p><ix:header>hid</ix:header></body></html>")
check("HTML 글만", "Net loss was $1,234" in t and "bad()" not in t and "hid" not in t)

# extract(가짜 fetch + 모의 응답)
DOC = "Item 1.01 Entry into a Material Definitive Agreement. On November 20, 2026 the Company sold 5,000,000 shares at $2.00 per share for gross proceeds of $10.0 million."
J.fetch = lambda u, **k: DOC
os.environ["LLM_MOCK_RESPONSE"] = json.dumps({"rows": [
    {"doc": "D1", "date": "2026-11-20", "form": "8-K", "item": "1.01", "amount": 10000000, "unit": "USD", "shares": 5000000, "price": 2.0,
     "quote": "sold 5,000,000 shares at $2.00 per share", "url": "wrong"},
    {"doc": "D1", "date": "", "form": "8-K", "item": "", "amount": None, "unit": "", "shares": None, "price": None,
     "quote": "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen", "url": "https://www.sec.gov/a.htm"}],
    "notes": ""})
res, path = J.extract(A(slug="zzzz-2026-11", urls="https://www.sec.gov/a.htm"))
check("extract ok", res["status"] == "ok" and len(res["rows"]) == 2)
check("url 바로잡음 + quote 원문에 있음", res["rows"][0]["url"] == "https://www.sec.gov/a.htm" and res["rows"][0]["quote_found"])
check("quote 15단어로 자름·원문에 없으면 false", res["rows"][1]["quote_trimmed"] and len(res["rows"][1]["quote"].split()) == 15 and not res["rows"][1]["quote_found"])
runs = list((tmp / "out" / "runs").rglob("extract-local.json"))
check("실행 기록(하루 상한용) 남김", len(runs) == 1 and json.loads(runs[0].read_text())["calls"] == 1)
runs[0].unlink()
r2, _ = J.extract(A(slug="zzzz-2026-11", urls="http://x.com/a"))
check("http 주소면 읽은 문서 없음", r2["status"] == "error")
r3, _ = J.extract(A(slug="zzzz-2026-11", urls=",".join(f"https://ex{i}.com/a" for i in range(7))))
check("주소 7개는 거절", r3["status"] == "error")
os.environ.pop("LLM_MOCK_RESPONSE")

# 하루·실행 상한(키가 있어도 네트워크 전에 멈춤)
day = J.datetime.now(J.timezone.utc).strftime("%Y-%m-%d")
(tmp / "out" / "runs" / day).mkdir(parents=True, exist_ok=True)
(tmp / "out" / "runs" / day / "shared-1.json").write_text(json.dumps({"calls": J.DAILY["shared"]}))
os.environ["ANTHROPIC_API_KEY"] = "test-not-a-key"
c = J.Caller("shared")
check("하루 상한이면 daily_cap", c.ask(system="s", user="u")["status"] == "daily_cap" and c.calls == 0)
c2 = J.Caller("extract")
c2.calls = J.PER_RUN["extract"]
check("실행 상한이면 run_cap", c2.ask(system="s", user="u")["status"] == "run_cap")
os.environ.pop("ANTHROPIC_API_KEY")
c3 = J.Caller("sns")
check("키 없으면 no_key(호출로 안 셈)", c3.ask(system="s", user="u")["status"] == "no_key" and c3.calls == 0)
(tmp / "out" / "runs" / day / "shared-1.json").unlink()

# task
r, _ = J.task(A(task="demo", prompt="요약: " + fake))
check("task 비밀값이면 refused, 값은 안 남김", r["status"] == "refused" and fake not in json.dumps(r, ensure_ascii=False))
r, _ = J.task(A(task="Bad Name", prompt="x"))
check("task 이름 검사", r["status"] == "error")
r, _ = J.task(A(task="demo", prompt="x" * 4001))
check("prompt 4000자 상한", r["status"] == "error")
r, _ = J.task(A(task="demo", prompt_path="scripts/llm.py"))
check("prompt_path 는 llm-tasks/ 아래만", r["status"] == "error")
r, _ = J.task(A(task="demo", prompt_path="llm-tasks/../scripts/llm.py"))
check("llm-tasks/.. 탈출 막음", r["status"] == "error")
r, _ = J.task(A(task="demo", prompt="a", prompt_path="llm-tasks/x.md"))
check("prompt·prompt_path 둘 다면 거절", r["status"] == "error")
check("스키마 additionalProperties 검사", J.schema_problem({"type": "object", "properties": {"a": {"type": "object"}}}) != ""
      and J.schema_problem({"type": "object", "additionalProperties": False, "properties": {}}) == "")
r, p = J.task(A(task="demo", prompt="한 줄 요약", mock=True, caller="healthworld"))
check("task 모의 ok·파일 이름", r["status"] == "ok" and p.name == "demo-local.json" and r["caller"] == "healthworld")
r, _ = J.task(A(task="demo", prompt="한 줄 요약", caller="Bad Caller"))
check("caller 형식 검사", r["status"] == "error")

# sns: 초안 → 대기열 형식 → 규칙 검사
files = J.build_queue("zzzz-2026-11", "ZZZZ", J.MOCK_SNS, ["2026-11-28T04:40-05:00", "2026-11-28T07:40-05:00"])
check("파일 이름 넷(관찰 글 없음)", set(files) == {"zzzz-2026-11.json", "zzzz-2026-11-th2.json", "zzzz-2026-11-igreels.json", "zzzz-2026-11-reels.json"})
check("th1 답글에 리포트 링크 1개", files["zzzz-2026-11.json"]["replies"][0]["text"].count("drkimworld.com/r/zzzz-2026-11/") == 1)
probs = J.check_files(files, "")
check("모의 초안은 규칙 통과", not any(probs.values()))
bad = dict(files["zzzz-2026-11-th2.json"], text="ZZZZ 요약 https://drkimworld.com #미국주식\n\n· 하나\n\n끝.")
ps = R.problems("x-th2.json", bad, "th2")
check("본문 링크·해시태그·요약 줄·마지막 질문 걸림", all(any(k in p for p in ps) for k in ("[T20③]", "[T20④]", "[T20⑦]", "[T20②]")))
ps = R.problems("x.json", dict(files["zzzz-2026-11.json"], poll=["아주아주아주긴보기입니다", "b"]), "th1")
check("투표 보기 25바이트", any("바이트" in p for p in ps))
ob = {"kind": "observe", "text": "오른 이유, 뉴스일까?\n\n주가는 99.9% 올랐다.\n\n여러분은 무엇을 먼저 보세요?", "hook": "질문",
      "topic_tag": "미국주식", "channels": ["threads"], "publish_at": "2026-11-28T04:40-05:00"}
check("관찰 글 숫자는 출처에 있어야", any("출처에 없음" in p for p in R.problems("x-obs.json", ob, "observe", "주가는 10% 올랐다")))
check("관찰 글 출처에 있으면 통과", R.problems("x-obs.json", ob, "observe", "주가는 99.9% 올랐다") == [])
check("관찰 글 KST 시간대 밖이면 걸림", any("[T20⑤]" in p for p in R.problems("x-obs.json", dict(ob, publish_at="2026-11-28T00:00-05:00"), "observe", "99.9")))
check("self_reply 금지어", any("self_reply 금지" in p for p in R.self_reply_problems("x", "지금 당장 매수할까요?")))
ad = "본문\n\n— 광고 —\n💊 차트를 오래 보시는 분이라면 루테인(광고): https://link.coupang.com/a/x\n이 포스팅은 쿠팡 파트너스 활동의 일환으로, 수수료를 받습니다."
check("AD2 바른 광고 문단 통과", R.ad2_problems("x", ad) == [])
check("AD2 구분선·링크 없으면 걸림", len(R.ad2_problems("x", "본문\n\n💊 루테인 광고")) >= 3)
igbad = dict(files["zzzz-2026-11-igreels.json"], text="첫 줄\n\nhttps://x.com #a #b #c #d #e #f")
check("인스타 URL·해시태그 6개 걸림", sum(1 for p in R.problems("x-igreels.json", igbad, "igreels") if "URL" in p or "해시태그" in p) >= 2)

# sns 전체(모의) — 리포트 파일이 있어야 함
rep = sorted(p.stem for p in J.REPORTS.glob("*.md") if not p.name.startswith("_"))[-1]
res, path = J.sns(A(slug=rep, mock=True))
check("sns 모의 실행 ok", res["status"] in ("ok", "ok_with_problems") and f"{rep}-th2.json" in res["files"])
res, _ = J.sns(A(slug="zzzz-none-2026-01", mock=True))
check("리포트 없으면 error", res["status"] == "error")
res, _ = J.sns(A(slug=rep, mock=True, facts="연락처 010-1234-5678"))
check("facts 개인정보면 refused", res["status"] == "refused")

# blogger 검사
fm = {"ticker": "ZZZZ", "data_as_of": "2026-11-20"}
body = "11월 20일 종가는 2.00달러였다. 과거 7번 중 5번 올랐다."
good = {"blog_slug": "zzzz offering stock analysis", "blog_intro": "가" * 250 + " 11월 20일 2.00달러",
        "blog_faq": [{"q": "첫 질문", "a": "a"}, {"q": "둘째 질문", "a": "a"}, {"q": "셋째 질문", "a": "7번 중 5번"}]}
check("블로거 바른 초안 통과(본문 길이 제외)", [p for p in J.blogger_problems("zzzz-none", fm, body, good) if "블로그 본문" not in p] == [])
badb = dict(good, blog_slug="ZZZZ 주가", blog_intro="짧음 이틀 만에 빚 3.5배 수익 보장", blog_faq=good["blog_faq"][:2])
pb = J.blogger_problems("zzzz-none", fm, body, badb)
check("블로거 K10·금지어·지어낸 숫자 걸림", all(any(k in p for p in pb) for k in ("blog_intro", "blog_faq", "blog_slug", "이틀", "빚", "수익 보장", "리포트에 없음")))
res, path, j = J.blogger(A(slug=rep, mock=True))
md = J.blogger_md(rep, res, j)
check("블로거 md 에 yaml 블록", "```yaml" in md and "blog_faq:" in md and res["calls"] == 1)

# 명령줄 dry(--no-write)는 파일을 쓰지 않음
before = set((tmp / "out").rglob("*"))
buf = io.StringIO()
with redirect_stdout(buf):
    rc = J.main(["task", "--task", "demo", "--prompt", "x", "--mock", "--no-write"])
check("dry 는 파일 안 씀", rc == 0 and set((tmp / "out").rglob("*")) == before and "STATUS=ok" in buf.getvalue())
check("키 없이 장부 안 생김", not Path(os.environ["LLM_USAGE_FILE"]).exists())

print(f"llm_jobs 검사 {ok}개 통과")
