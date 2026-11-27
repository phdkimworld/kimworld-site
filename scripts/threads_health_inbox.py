#!/usr/bin/env python3
"""Threads @drkimworld(건강월드) 댓글 자동 관리 — 운영자 2026-11-27 "댓글 체크 자주 하되 토큰 사용 줄일 방법".

세션을 깨우지 않고 GitHub Actions 가 20분마다 돈다:
  1) 최근 14일 우리 원글의 대화(conversation)에서 남이 단 글 중 아직 답 안 한 것만 고른다 — 새 글이 없으면 모델을 부르지 않고 끝(비용 0).
  2) 약·질환·임신·아이·진단 등 개인 의료 판단이 필요한 글, 너무 길거나 링크가 있는 글은 답하지 않고 '세션 확인' 목록(flagged)에 남긴다.
  3) 나머지는 저가 모델이 합쇼체로 짧게 답 → 규칙 검사(길이·링크·금지어·질병 효능·숫자가 식약처 근거에 있는지) 통과분만 게시.
장부: social/llm/threads_health/state.json {answered: {답글id: 우리답id}, flagged: {답글id: 사유·글}, skipped: {...}}
세션(건강월드 매일 운영)은 flagged 만 읽는다. 값·토큰은 출력하지 않는다.
"""
import json, os, re, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import llm  # noqa: E402
from llm_jobs import Caller, secret_hits  # noqa: E402

API = "https://graph.threads.net/v1.0"
STATE = ROOT / "social/llm/threads_health/state.json"
TOK = os.environ.get("DRKIM_THREADS_ACCESS_TOKEN", "")
FLAG = re.compile(r"약을|약 먹|복용|처방|진단|수술|암|당뇨|고혈압|혈압약|신장|간 수치|임신|수유|아기|아이|어린이|부작용|병원|검사 결과|수치가")
# 광고성 댓글(운영자 11-27 "광고성 댓글 다는 애들 다 차단 및 삭제"): API로는 남의 댓글 삭제·계정 차단이 안 되므로 '숨김'(manage_reply hide)으로 처리하고
# 아이디를 장부 spam 에 모아 운영자가 앱에서 차단하게 한다.
SPAM = re.compile(r"https?://|www\.|\.com|\.kr|오픈채팅|오픈톡|카톡|카카오톡|텔레그램|DM\s?주|디엠|부업|재택|수익\s?인증|월\s?\d+\s?만|투자\s?리딩|코인|리딩방|대출|협찬|체험단|공구|공동구매|할인\s?코드|쿠폰|프로필\s?(링크|확인)|맞팔|선팔|팔로우\s?(해|하면|부탁)", re.I)
BAD = re.compile(r"https?://|쿠팡|구매|추천 제품|치료|예방|완화|낫|꼭 드세요|필수|놀라운|충격|최고|완벽")
SYSTEM = """너는 영양제 뒷면 표기를 식약처 기준으로 읽어 주는 '김박사'(의사·약사 아님)의 Threads 계정이다. 남이 단 댓글에 답한다.
합쇼체(~입니다·~하십시오), 2~4문장, 200자 이내. 그분 상황에 맞는 확인 포인트 1~2개(아래 식약처 근거의 숫자·문구만) + 대화를 잇는 짧은 질문 하나로 끝.
금지: 링크, '쿠팡'·'구매'·제품 추천, 질병 치료·예방·완화·개선 암시, 근거에 없는 숫자, 개인 진단, 재촉, 과장어, 이모지. 감사 인사만 하고 끝내지 않는다."""


def call(method, path, params):
    params = dict(params, access_token=TOK)
    q = urllib.parse.urlencode(params)
    url = f"{API}/{path}?{q}" if method == "GET" else f"{API}/{path}"
    req = urllib.request.Request(url, data=None if method == "GET" else q.encode(), method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def facts_for(text):
    import yaml
    y = yaml.safe_load(open(ROOT / "health/health.yaml"))
    gs = y.get("guides") or y.get("ingredients")
    gs = gs if isinstance(gs, list) else list(gs.values())
    out = []
    for g in gs:
        names = [g.get("name", "")] + re.split(r"[,(·)]", g.get("aka", "") or "")
        if any(n and n.strip() and n.strip() in text for n in names):
            f = "; ".join(f"{x['text']} — {x['dose']}" for x in g.get("functions", []))
            out.append(f"[{g.get('name')}] 식약처 기능: {f} / 고를 때: {' '.join(g.get('choose', []))} / 주의: {' '.join(g.get('cautions', []))}")
    return "\n".join(out[:4])


def check(ans, facts):
    if not ans or len(ans) > 300 or BAD.search(ans) or secret_hits(ans):
        return "길이·링크·금지어"
    for n in re.findall(r"\d[\d,.]*", ans):
        if n.replace(",", "") not in facts.replace(",", "") and n not in ("1", "2", "3", "4"):
            return f"근거에 없는 숫자 {n}"
    return ""


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {"answered": {}, "flagged": {}, "skipped": {}}


def review():
    """복기(운영자 11-27 '30일 루틴' — 전날 성과 매일 10분 복기·잘된 훅 모아두기): 최근 14일 원글 지표를 표로. 모델 안 부름."""
    rows = []
    for t in call("GET", "me/threads", {"fields": "id,text,timestamp", "limit": 40}).get("data", []):
        try:
            m = {d["name"]: (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value", 0))
                 for d in call("GET", f"{t['id']}/insights", {"metric": "views,likes,replies,reposts,quotes"}).get("data", [])}
        except Exception:
            m = {}
        rows.append({"id": t["id"], "at": t["timestamp"][:16], "hook": (t.get("text") or "").split("\n")[0][:60], **m})
    rows.sort(key=lambda r: -(r.get("views") or 0))
    out = ROOT / "social/llm/threads_health/review.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="minutes"), "posts": rows[:20]}, ensure_ascii=False, indent=1) + "\n")
    cf = os.environ.get("CHANGED_FILE")
    if cf:
        Path(cf).write_text(str(out.relative_to(ROOT)) + "\n")
    for r in rows[:5]:
        print(f"  조회 {r.get('views')} 좋아요 {r.get('likes')} 댓글 {r.get('replies')} | {r['hook']}")
    return 0


def main():
    dry = "--dry" in sys.argv
    if "--review" in sys.argv and TOK:
        return review()
    if not TOK:
        print("::notice::DRKIM_THREADS_ACCESS_TOKEN 없음 — 건너뜀"); return 0
    st = load(); seen = set(st["answered"]) | set(st["flagged"]) | set(st["skipped"]) | set(st.get("spam", {}))
    me = call("GET", "me", {"fields": "id,username"})
    since = datetime.now(timezone.utc) - timedelta(days=14)
    roots = [t for t in call("GET", "me/threads", {"fields": "id,text,timestamp", "limit": 40}).get("data", [])
             if datetime.strptime(t["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) >= since]
    new = []
    for t in roots:
        for x in call("GET", f"{t['id']}/conversation", {"fields": "id,text,username,timestamp", "reverse": "false"}).get("data", []):
            if x.get("username") != me.get("username") and x["id"] not in seen:
                new.append((t, x))
    print(f"원글 {len(roots)} · 새 답글 {len(new)}")
    if not new:
        return 0
    caller = Caller("shared", mock=dry); changed = False
    for t, x in new[:6]:
        txt = (x.get("text") or "").strip()
        if SPAM.search(txt):
            if not dry:
                try:
                    call("POST", f"{x['id']}/manage_reply", {"hide": "true"})
                    hid = True
                except Exception:
                    hid = False
            else:
                hid = False
            st.setdefault("spam", {})[x["id"]] = {"who": x.get("username"), "text": txt[:200], "hidden": hid, "at": x.get("timestamp")}
            changed = True; print(f"::notice::광고성 댓글 숨김 @{x.get('username')} ({'숨김' if hid else '숨김 실패'})"); continue
        if len(txt) < 4 or re.fullmatch(r"[\W\d_ㅋㅎ]+", txt):
            st["skipped"][x["id"]] = {"why": "짧음·이모지", "at": x.get("timestamp")}; changed = True; continue
        if FLAG.search(txt) or re.search(r"https?://", txt) or len(txt) > 400:
            st["flagged"][x["id"]] = {"why": "의료 판단·링크·긴 글 — 세션 확인", "who": x.get("username"), "text": txt[:300], "root": t["id"]}; changed = True; continue
        facts = facts_for((t.get("text") or "") + " " + txt) or facts_for("오메가3 비타민D 마그네슘")
        r = caller.ask(system=SYSTEM, user=f"우리 원글: {(t.get('text') or '')[:400]}\n댓글: {txt}\n\n식약처 근거:\n{facts}", tier="cheap", max_tokens=1200)  # 400은 잘림(11-27 실측)
        ans = (r.get("text") or "").strip()
        why = r["status"] if r["status"] != "ok" else check(ans, facts)
        if why:
            st["flagged"][x["id"]] = {"why": f"자동 답 실패: {why}", "who": x.get("username"), "text": txt[:300], "draft": ans[:300], "root": t["id"]}; changed = True; continue
        if dry:
            print(f"[dry] {x['id']} → {ans}"); continue
        c = call("POST", "me/threads", {"media_type": "TEXT", "text": ans, "reply_to_id": x["id"]})
        time.sleep(5)
        p = call("POST", "me/threads_publish", {"creation_id": c["id"]})
        st["answered"][x["id"]] = {"answer": p.get("id"), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        changed = True
        print(f"::notice::답함 {x['id']} → {p.get('id')}")
    if changed and not dry:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n")
        cf = os.environ.get("CHANGED_FILE")
        if cf:
            Path(cf).write_text(str(STATE.relative_to(ROOT)) + "\n")
    caller.log(ROOT / "social/llm/threads_health/last.json", caller.last or "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
