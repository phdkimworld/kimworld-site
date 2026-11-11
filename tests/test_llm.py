"""모델 호출 도우미·댓글 답글 검사·심사·주간 메모 검사(네트워크 없이, 키 없이)."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
tmp = Path(tempfile.mkdtemp())
os.environ["LLM_USAGE_FILE"] = str(tmp / "usage.json")
os.environ["LLM_DELTA_FILE"] = str(tmp / "delta.json")
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("LLM_MOCK_RESPONSE", None)
import llm  # noqa: E402
import comment_ai as ca  # noqa: E402
import llm_judge as lj  # noqa: E402
import weekly_ai as wa  # noqa: E402

ok = 0


def check(name, cond):
    global ok
    if not cond:
        print("FAIL", name)
        sys.exit(1)
    ok += 1
    print("  ok ", name)


# 키 없음 = 건너뜀
r = llm.ask("comments", "s", "u")
check("키 없으면 no_key", r["status"] == "no_key" and "no_key" in llm.SKIP_STATUSES and "no_credit" in llm.SKIP_STATUSES)
check("키 없으면 장부 없음", not Path(os.environ["LLM_USAGE_FILE"]).exists())

# 비용·장부
check("저가 모델 단가", abs(llm.cost("claude-haiku-5-5", 50_000, 50_000) - 0.03) < 1e-9)
check("저가 모델 긴 입력 단가", abs(llm.cost("claude-haiku-5-5", 200_000, 0) - 0.10) < 1e-9)
check("판단용 모델 단가", abs(llm.cost("claude-sonnet-5-5", 1_000_000, 100_000) - 3.0) < 1e-9)
check("모르는 모델은 비싸게", llm.cost("x", 1_000_000, 0) >= 5.0)
check("캐시 읽기는 10%", abs(llm.cost("claude-sonnet-5-5", 0, 0, cache_read=1_000_000) - 0.2) < 1e-9)
d = llm.usage_from_response({"model": "claude-haiku-5-5", "usage": {"input_tokens": 1000, "output_tokens": 100}}, "claude-haiku-5-5")
check("응답 usage 셈", d["in"] == 1000 and d["out"] == 100 and d["calls"] == 1)
d2 = llm.usage_from_response({"model": "claude-sonnet-5", "usage": {"iterations": [{"input_tokens": 10, "output_tokens": 0}, {"input_tokens": 10, "output_tokens": 5}]}}, "claude-sonnet-5-5")
check("서버 대체 iterations 합산", d2["in"] == 20 and d2["out"] == 5)
book = {}
llm.add_usage(book, "2026-11", "comments", {"calls": 1, "in": 5, "out": 1, "usd": 1.5})
llm.add_usage(book, "2026-11", "judge", {"calls": 1, "in": 5, "out": 1, "usd": 2.0})
check("기능별·전체 합", llm.spent(book, "2026-11", "comments") == 1.5 and llm.spent(book, "2026-11") == 3.5)
check("기본 예산", llm.budget("comments") == 40 and llm.budget("judge") == 25 and llm.budget("weekly") == 10 and llm.total_cap() == 120)

# 예산 넘으면 부르지 않음(키가 있어도 네트워크 전에 멈춤)
llm.save_usage({"months": {llm.month_key(): {"usd": 39.999, "features": {"comments": {"usd": 39.999}}}}})
os.environ["ANTHROPIC_API_KEY"] = "test-not-a-key"
r = llm.ask("comments", "s", "x" * 1000, max_tokens=2000)
check("기능 예산 넘으면 budget", r["status"] == "budget")
llm.save_usage({"months": {llm.month_key(): {"usd": 119.99, "features": {"judge": {"usd": 1}}}}})
r = llm.ask("weekly", "s", "x" * 1000, tier="judge", max_tokens=2000)
check("전체 상한 넘으면 budget", r["status"] == "budget")
llm._STOP["status"] = "no_credit"
llm.save_usage({"months": {}})
r = llm.ask("comments", "s", "u")
check("크레딧 없음이 나온 뒤에는 부르지 않음", r["status"] == "no_credit")
llm._STOP["status"] = ""
del os.environ["ANTHROPIC_API_KEY"]

# 모의 응답
os.environ["LLM_MOCK_RESPONSE"] = '{"category":"question","reply":"x"}'
r = llm.ask("comments", "s", "u", schema=ca.SCHEMA)
check("모의 응답 JSON", r["status"] == "ok" and r["json"]["category"] == "question")
del os.environ["LLM_MOCK_RESPONSE"]

# 댓글 거르기
check("감사는 hourly 몫", ca.prefilter("좋은 영상 감사합니다") == "감사")
check("AI 질문은 세션 몫", ca.prefilter("이거 AI가 쓴 거죠?") == "AI여부")
check("홍보는 세션 몫", ca.prefilter("수익 보장 리딩방 문의") == "홍보의심")
check("투표는 세션 몫", ca.prefilter("2번") == "투표")
check("질문은 모델 대상", ca.prefilter("장부가는 왜 줄었나요?") is None)

REPORT = "---\nticker: AGNC\ndata_as_of: 2026-11-10\n---\n9월 말 한 주당 장부가 7.13달러로 6월 말보다 16.9% 줄었습니다. 11월 10일 종가 8.74달러는 새 장부의 1.23배입니다. 3부 기록표"
good = "11월 10일 종가 8.74달러는 9월 말 장부 7.13달러의 1.23배였습니다. 과거 비교는 리포트 3부 기록표에 있습니다. 배당도 궁금하세요?"
check("통과하는 답글", ca.check_reply(good, REPORT, "agnc-2026-11") == [])
check("링크는 허용 주소만", ca.check_reply(good + " https://drkimworld.com/r/agnc-2026-11/", REPORT, "agnc-2026-11") == [])
check("다른 링크 거절", any("링크" in e for e in ca.check_reply(good + " https://x.com/a", REPORT, "agnc-2026-11")))
check("리포트에 없는 숫자 거절", any("숫자" in e for e in ca.check_reply("11월 10일 기준 장부는 7.5달러입니다.", REPORT, "agnc-2026-11")))
check("리포트에 없는 날짜 거절", any("날짜" in e for e in ca.check_reply("12월 3일 기준 1.23배입니다.", REPORT, "agnc-2026-11")))
check("기준 날짜 없으면 거절", any("기준 날짜" in e for e in ca.check_reply("장부의 1.23배입니다.", REPORT, "agnc-2026-11")))
check("150자 넘으면 거절", any("자 >" in e for e in ca.check_reply("11월 10일 기준 " + "가" * 150, REPORT, "agnc-2026-11")))
for bad, why in [("지금 매수하세요", "권유"), ("목표가는", "목표가"), ("수익 보장", "수익"), ("올인", "베팅"), ("저도 보유하고 있어요", "보유"),
                 ("AI가 정리", "AI"), ("회원 가입하면", "가입"), ("사기입니다", "사기"), ("빚내서", "빚"), ("A → B", "화살표")]:
    errs = ca.check_reply(f"11월 10일 기준 {bad}", REPORT, "agnc-2026-11")
    check(f"금지: {why}", any(why in e for e in errs))
check("로봇 회사는 AI 언급 아님", not any("AI" in e for e in ca.check_reply("11월 10일 기준 로봇 회사입니다.", REPORT, "agnc-2026-11")))
check("가운뎃점 나열 거절", any("가운뎃점" in e for e in ca.check_reply("11월 10일 기준 A·B·C", REPORT, "agnc-2026-11")))

# 리포트 찾기
reps = [{"slug": "agnc-2026-10", "ticker": "AGNC", "date": "2026-10-13", "youtube_id": "aaaaaaaaaaa"},
        {"slug": "agnc-2026-11", "ticker": "AGNC", "date": "2026-11-11", "youtube_id": "bbbbbbbbbbb"}]
check("옛 영상도 같은 종목 최신 리포트", ca.report_for_video(reps, "aaaaaaaaaaa", "")["slug"] == "agnc-2026-11")
check("제목 티커로 찾기", ca.report_for_video(reps, "zzz", "장부가 줄었는데 왜 #AGNC")["slug"] == "agnc-2026-11")
check("못 찾으면 None", ca.report_for_video(reps, "zzz", "다른 이야기") is None)
check("slug 로 최신 리포트", ca.report_for_slug(reps, "agnc-2026-10")["slug"] == "agnc-2026-11")

# 심사: 원고에 없는 인용은 버림(모의 응답)
rp = tmp / "x-2026-11.md"
rp.write_text("---\nticker: X\n---\n결국 주가는 오를 것입니다. 국면 B 에서는 달랐습니다.\n", encoding="utf-8")
os.environ["LLM_MOCK_RESPONSE"] = json.dumps({"overall": "짧음", "items": [
    {"principle": "주장 크기", "quote": "결국 주가는 오를 것입니다", "why": "근거 없음", "fix": "근거 숫자를 앞에"},
    {"principle": "정의 전 사용", "quote": "원고에 없는 문장", "why": "-", "fix": "-"}]}, ensure_ascii=False)
st, md = lj.judge(rp)
check("심사 결과 형식", st == "ok" and "결국 주가는 오를 것입니다" in md and "원고에 없는 문장" not in md and "버림" in md)
del os.environ["LLM_MOCK_RESPONSE"]
check("키 없으면 심사 건너뜀(0)", lj.main([str(rp), "--out", str(tmp / "j.md")]) == 0 and not (tmp / "j.md").exists())

# 주간 메모: 비공개 숫자 줄 지움
md, cut = wa.scrub("## 요약\n- 페이지뷰 지난주보다 12% 늘었다\n- 쿠팡 수수료 3,000원\n- 애드핏 클릭 4번")
check("수익·광고 줄 지움", cut == 2 and "페이지뷰" in md and "쿠팡" not in md)

print(f"test_llm: {ok} 통과")
