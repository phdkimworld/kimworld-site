#!/usr/bin/env python3
"""새 리포트를 구글 블로거(김박사 월드 노트)에 짧은 소개 글로 올린다.

운영자 요청 2026-10-25(구글 노출 보조). 리포트를 그대로 옮기지 않는다: 요약·핵심 3줄·차트·영상·리포트 링크만.
운영자 지시 2026-10-25 "최대한 많이 올려줘": 하루 최대 BLOGGER_DAILY(기본 40)건, 한 번 실행에 BLOGGER_PER_RUN(기본 3)건을 BLOGGER_GAP(기본 60)초 간격으로,
최신 리포트부터 지난 리포트까지(BLOGGER_DAYS 기본 3650일) 올린다. 구글은 공식 한도를 밝히지 않으며 보고된 경험치는 하루 약 50건·짧은 시간 연속 4~6건이다.
구글이 403/429(한도)로 막으면 그 실행은 멈추고(실패 아님) 다음 실행에서 이어 간다. 이미 올린 건 다시 올리지 않는다.
올린 기록: social/blogger/posted.json {slug: {"url":…, "at":…}} (공개 저장소에는 주소·시각만)

환경변수: GOOGLE_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN, BLOGGER_BLOG_ID
선택: SLUG(그 리포트 하나만), DRY=1(올리지 않고 내용만 출력), BLOGGER_DAILY, BLOGGER_PER_RUN, BLOGGER_GAP, BLOGGER_DAYS
"""
import datetime as dt
import html
import re
import time
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "content" / "reports"
STATE = ROOT / "social" / "blogger" / "posted.json"
SITE = yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))
BASE = SITE["site_url"].rstrip("/")
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")


def front(p: Path) -> dict:
    t = p.read_text(encoding="utf-8")
    if not t.startswith("---"):
        return {}
    return yaml.safe_load(re.split(r"^---\s*$", t, maxsplit=2, flags=re.M)[1]) or {}


def short_title(fm: dict) -> str:
    """검색형 제목: '<이름>(<티커>) 주가 분석 — <훅>'. 블로거 글 33건이 7일 동안 사이트 세션 0(2026-10-26 통합 인사이트)이라
    블로그 검색에서 사람들이 치는 말(이름·티커·주가)을 맨 앞에 둔다(사이트 검색 제목 seo_fields와 같은 꼴)."""
    t = str(fm.get("title") or "").split(" | ")[0].strip()
    tk = str(fm.get("ticker") or "").strip()
    m = re.match(r"^([^,，]{1,20})[,，]\s*(.+)$", t)
    if not (m and tk):
        return t[:140]
    name, hook = m.group(1).strip(), m.group(2).strip()
    kind = "코인 시세" if "가격" in str(fm.get("title") or "") else "주가"
    head = name if name.upper() == tk.upper() else f"{name}({tk})"
    return f"{head} {kind} 분석 — {hook}"[:140]


def tickers_yaml() -> dict:
    p = ROOT / "data" / "tickers.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


def slug_en(slug: str, fm: dict) -> str:
    """영문 고유주소(블로그 SEO 지침 7.2①, 2026-10-29): 한글 제목을 그대로 넘기면 한글이 빠져 'slnh-85-28-19.html'이 된다.
    처음 게시할 때 영문 제목으로 올려 주소를 만들고(블로거는 첫 제목으로 주소를 정한다) 곧바로 한글 제목으로 바꾼다."""
    if fm.get("blog_slug"):
        return re.sub(r"[^a-z0-9]+", " ", str(fm["blog_slug"]).lower()).strip()
    tk = str(fm.get("ticker") or "").lower()
    en = str((tickers_yaml().get(str(fm.get("ticker") or "")) or {}).get("name_en") or "")
    words = [w for w in re.sub(r"[^a-z0-9 ]+", " ", en.lower()).split() if w not in ("inc", "corp", "corporation", "ltd", "plc", "co", "the", "holdings")][:3]
    return " ".join([tk] + words + ["stock", "analysis"])


def related(fm: dict) -> list:
    """연관 종목 티커(파트너·비교 대상): related_tickers 또는 share_numbers 라벨 가운데 대문자 티커."""
    tk = str(fm.get("ticker") or "")
    out = [str(x) for x in (fm.get("related_tickers") or [])]
    for x in fm.get("share_numbers") or []:
        lab = str(x).rsplit(None, 1)[0]
        if re.fullmatch(r"[A-Z]{1,5}", lab) and lab != tk:
            out.append(lab)
    return list(dict.fromkeys(out))


def faq(fm: dict, slug: str) -> list:
    """'이 리포트가 답하는 3가지 질문': blog_faq(제작 때 블로그 전용으로 쓴 질문·답)가 있으면 그것, 없으면 1~6부 '핵심' 콜아웃에서 셋."""
    if fm.get("blog_faq"):
        return [(str(x.get("q", "")), str(x.get("a", ""))) for x in fm["blog_faq"]][:3]
    md = (REPORTS / f"{slug}.md").read_text(encoding="utf-8")
    md = re.split(r"^---\s*$", md, maxsplit=2, flags=re.M)[-1]
    out = []
    for m in re.finditer(r"^## ([2-5])부\.\s*(.+?)\n+> \*\*핵심:\*\*\s*(.+)$", md, re.M):
        out.append((m.group(2).strip().rstrip("?") + "?", m.group(3).strip()))
    return out[:3]


def more_reports(slug: str, fm: dict, n: int = 3) -> list:
    """블로그 → 사이트 입구 늘리기(유입 실험 2026-11-05, 블로거 글 130개인데 7일 유입 0):
    같은 종목의 다른 리포트, 그다음 같은 테마 리포트를 최신순으로 n개(공개된 것만)."""
    tk, th = str(fm.get("ticker") or ""), str(fm.get("theme") or "")
    today = dt.datetime.now(ET).date()
    same, theme = [], []
    for p in REPORTS.glob("*.md"):
        if p.stem == slug:
            continue
        f = front(p)
        if not f or f.get("draft"):
            continue
        try:
            d = dt.date.fromisoformat(str(f.get("date"))[:10])
        except ValueError:
            continue
        if d > today:
            continue
        if tk and str(f.get("ticker") or "") == tk:
            same.append((d, p.stem, f))
        elif th and str(f.get("theme") or "") == th:
            theme.append((d, p.stem, f))
    same.sort(key=lambda x: x[0], reverse=True)
    theme.sort(key=lambda x: x[0], reverse=True)
    return [(s, short_title(f)) for _, s, f in (same + theme)[:n]]


CPAS_MARK = "<!--kw-cpas-->"
CPAS_DISCLOSURE = "이 영역은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


def cpas_block() -> str:
    """쿠팡 파트너스 다이내믹 배너 한 칸(운영자 지시 2026-11-04 "쿠파스만 해서 일단 여기도 관리").
    사이트로 가는 버튼·영상 뒤, 면책 문구 앞에 하나만. 하위 ID "blogger"로 쿠팡 실적을 따로 센다.
    블로거 글 본문에서는 스크립트 대신 쿠팡이 만드는 iframe 주소를 바로 넣는다(피드·앱 보기에서도 같게)."""
    src = ("https://ads-partners.coupang.com/widgets.html?id=1038868&template=carousel&trackingCode=AF4489672"
           "&subId=blogger&width=680&height=140&tsource=")
    return (f'{CPAS_MARK}<div style="margin:22px 0 8px">'
            f'<iframe src="{src}" width="680" height="140" frameborder="0" scrolling="no" referrerpolicy="unsafe-url" '
            f'style="max-width:100%;border:0" title="쿠팡 추천 상품"></iframe>'
            f'<p style="color:#888;font-size:12px;margin:4px 0 0">{CPAS_DISCLOSURE}</p></div>')


ADFIT_MARK = "<!--kw-adfit-->"
# 애드핏 매체 '김박사 월드 블로그'(phdkimworld.blogspot.com)의 300x250 단위(운영자 생성 2026-11-06). 비우면 넣지 않는다
BLOGGER_ADFIT_UNIT = os.environ.get("BLOGGER_ADFIT_UNIT") or "DAN-djnM2vIZK3qhEHJR"


def adfit_block() -> str:
    """애드핏 300x250 한 칸: 사이트로 가는 버튼·영상 뒤, 쿠팡 배너 앞. 한 글에 한 번(애드핏 단위는 한 페이지 한 번)."""
    if not BLOGGER_ADFIT_UNIT:
        return ""
    return (f'{ADFIT_MARK}<div style="margin:22px 0 0;text-align:center">'
            f'<ins class="kakao_ad_area" style="display:none;" data-ad-unit="{BLOGGER_ADFIT_UNIT}" data-ad-width="300" data-ad-height="250"></ins>'
            f'<script type="text/javascript" src="//t1.daumcdn.net/kas/static/ba.min.js" async></script></div>')


def body(slug: str, fm: dict) -> str:
    u = f"{BASE}/r/{slug}/?utm_source=blogger&utm_medium=post&utm_campaign={slug}"
    e = html.escape
    tk = e(str(fm.get("ticker") or ""))
    name = e(str((tickers_yaml().get(str(fm.get("ticker") or "")) or {}).get("name") or tk))
    hook = e(str(fm.get("title") or "").split(" | ")[0].split(",", 1)[-1].strip())
    rel = related(fm)
    rel_txt = f" · 연관 종목 {', '.join(rel)}" if rel else ""
    # 대표 그림 alt: 종목명·티커·핵심 사건(지침 7.2③)
    alt = f"{name}({tk}) 주가 분석 - {hook}{rel_txt}"
    # v2.9 2.5②(운영자 11-02 LAES 블로그 검수): 블로거 기본 테마에서도 본문과 구분되게 인라인 스타일 고정
    box = lambda label: (f'<div style="margin:22px 0;padding:16px;background-color:#f8f9fa;border-left:4px solid #ff6b00;border-radius:6px">'
                         f'<p style="margin:0 0 8px 0;font-weight:bold">{label}</p>'
                         f'<a href="{u}" style="display:inline-block;padding:9px 16px;background-color:#ff6b00;color:#ffffff;text-decoration:none;font-weight:bold;border-radius:4px">전체 분석 리포트 무료로 보기 →</a></div>')
    intro = str(fm.get("blog_intro") or fm.get("summary") or "")
    parts = [
        f'<p><a href="{u}"><img src="{BASE}/og/{slug}.png" alt="{e(alt)}" style="max-width:100%;height:auto;border-radius:8px"></a></p>',
        f"<p>{e(intro)}</p>",
    ]
    kp = [str(x) for x in (fm.get("key_points") or [])][:3]
    if kp:
        parts.append(f"<h3>📊 {name}({tk}) 핵심 3줄 요약</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in kp) + "</ul>")
    parts.append(box(f"📈 날짜별 기록표와 시나리오별 가능성은 리포트에서"))
    qs = faq(fm, slug)
    if qs:
        parts.append("<h3>🔍 이 리포트가 답하는 3가지 질문</h3><ol>" + "".join(f"<li><strong>{e(q)}</strong> {e(a)}</li>" for q, a in qs) + "</ol>")
    yid = str(fm.get("youtube_id") or "").strip()
    if len(yid) == 11:
        parts.append(
            f"<h3>🎥 영상으로 보는 {name}({tk}) 주가 미스터리</h3>"
            f'<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;max-width:100%;margin-bottom:20px">'
            f'<iframe src="https://www.youtube.com/embed/{yid}" title="{name}({tk}) 주가 분석 영상" style="position:absolute;top:0;left:0;width:100%;height:100%;border:0" allowfullscreen></iframe></div>'
        )
    more = more_reports(slug, fm)
    if more:
        parts.append(f"<h3>📚 함께 보면 좋은 {name}·{e(str(fm.get('theme') or '같은 테마'))} 리포트</h3><ul>" + "".join(
            f'<li><a href="{BASE}/r/{s}/?utm_source=blogger&amp;utm_medium=post&amp;utm_campaign={slug}&amp;utm_content=related">{e(t)}</a></li>'
            for s, t in more) + "</ul>")
    parts.append(box("🧾 매매 전 체크리스트와 지난 예측 성적표까지 무료"))
    parts.append(adfit_block())
    parts.append(cpas_block())
    parts.append(
        f'<p style="color:#888;font-size:13px">숫자 기준일 {e(str(fm.get("data_as_of") or ""))}. '
        "공개 공시와 시세를 정리한 교육용 글이며 특정 종목의 매수·매도를 권하지 않습니다. "
        f'다른 미국주식 분석: <a href="{BASE}/?utm_source=blogger&utm_medium=post">김박사 월드 홈페이지</a></p>'
    )
    out = "\n".join(parts)
    n = len(re.sub(r"<[^>]+>", "", html.unescape(out)))
    if n < 700:
        print(f"::warning title=블로그 본문 짧음::{slug} {n}자 < 700 — blog_intro·blog_faq를 머리말에 넣는다(지침 7.2②)")
    return out


def token() -> str:
    """클라이언트 ID·보안 비밀번호 조합을 차례로 시도한다(블로거 전용 비밀번호 → 사이트 구글 로그인 비밀번호).
    갱신 토큰은 OAuth 클라이언트에 묶여 있고, 같은 클라이언트의 사용 중인 비밀번호라면 어느 것이든 통한다."""
    rt = os.environ["BLOGGER_REFRESH_TOKEN"].strip().strip("\"'")
    ids = [os.environ.get("GOOGLE_CLIENT_ID", ""), os.environ.get("GOOGLE_CLIENT_ID_SECRET", "")]
    secs = [("BLOGGER_CLIENT_SECRET", os.environ.get("BLOGGER_CLIENT_SECRET", "")), ("GOOGLE_CLIENT_SECRET", os.environ.get("GOOGLE_CLIENT_SECRET", ""))]
    last = None
    for cid in dict.fromkeys(i.strip() for i in ids if i.strip()):
        for name, sec in secs:
            sec = sec.strip().strip("\"'")
            if not sec:
                continue
            data = urllib.parse.urlencode({"client_id": cid, "client_secret": sec, "refresh_token": rt, "grant_type": "refresh_token"}).encode()
            try:
                with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data), timeout=30) as r:
                    tok = json.load(r)["access_token"]
                print(f"::notice title=블로거 인증::{name} + 클라이언트 {cid[:12]}… 로 성공")
                return tok
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")[:300].replace("\n", " ")
                print(f"::warning title=블로거 인증 실패::{name} + 클라이언트 {cid[:12]}… → {e.code} {body}")
                last = e
    raise SystemExit("블로거 인증 실패(위 경고 참고)") if last is None else SystemExit(1)


def api(tok: str, method: str, path: str, data=None) -> dict:
    bid = os.environ["BLOGGER_BLOG_ID"]
    req = urllib.request.Request(f"https://www.googleapis.com/blogger/v3/blogs/{bid}/posts/{path}", method=method,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def publish(tok: str, title: str, content: str, labels: list, en: str = "") -> str:
    """영문 제목(en)으로 먼저 올려 영문 주소를 만들고, 곧바로 한글 제목으로 바꾼다(주소는 그대로 남는다)."""
    post = api(tok, "POST", "", {"kind": "blogger#post", "title": en or title, "content": content, "labels": labels})
    if en and en != title:
        post = api(tok, "PATCH", post["id"], {"title": title})
    return post.get("url", "")


def update(tok: str, url: str, title: str, content: str, labels: list) -> str:
    """이미 올린 글의 본문·라벨만 새 틀로 바꾼다(주소는 못 바꾼다)."""
    path = urllib.parse.urlparse(url).path
    post = api(tok, "GET", "bypath?" + urllib.parse.urlencode({"path": path}))
    return api(tok, "PATCH", post["id"], {"title": title, "content": content, "labels": labels}).get("url", url)


def backfill_ads(tok: str, limit: int) -> int:
    """이미 올린 글에 쿠팡 칸이 없으면 면책 문구 앞(없으면 맨 끝)에 넣는다. 한 번에 limit개."""
    bid = os.environ["BLOGGER_BLOG_ID"]
    H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    done, page = 0, ""
    while done < limit:
        q = urllib.parse.urlencode({"maxResults": 50, "fetchBodies": "true", "status": "live", **({"pageToken": page} if page else {})})
        with urllib.request.urlopen(urllib.request.Request(f"https://www.googleapis.com/blogger/v3/blogs/{bid}/posts?{q}", headers=H), timeout=60) as r:
            js = json.load(r)
        for it in js.get("items") or []:
            c = it.get("content") or ""
            if "drkimworld.com" not in c:
                continue
            nc = c
            if CPAS_MARK not in nc:
                i = nc.rfind('<p style="color:#888;font-size:13px">')
                nc = (nc[:i] + cpas_block() + nc[i:]) if i >= 0 else (nc + cpas_block())
            if BLOGGER_ADFIT_UNIT and ADFIT_MARK not in nc:  # 애드핏은 쿠팡 칸 바로 앞(2026-11-06)
                i = nc.find(CPAS_MARK)
                nc = nc[:i] + adfit_block() + nc[i:]
            if nc == c:
                continue
            req = urllib.request.Request(f"https://www.googleapis.com/blogger/v3/blogs/{bid}/posts/{it['id']}", data=json.dumps({"content": nc}).encode(), headers=H, method="PATCH")
            try:
                with urllib.request.urlopen(req, timeout=60):
                    pass
            except urllib.error.HTTPError as ex:
                if ex.code in (403, 429):
                    print(f"::warning title=블로거 쿠팡 칸::한도 {ex.code}, {done}건에서 멈춤(다음 실행에서 이어 감)")
                    return done
                raise
            done += 1
            time.sleep(2)
            if done >= limit:
                break
        page = js.get("nextPageToken") or ""
        if not page:
            break
    print(f"::notice title=블로거 쿠팡 칸::기존 글 {done}건에 넣음(쿠팡·애드핏)")
    return done


def live(slug: str) -> bool:
    try:
        req = urllib.request.Request(f"{BASE}/r/{slug}/", method="HEAD", headers={"User-Agent": "kimworld-blogger"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> int:
    if os.environ.get("ADS_BACKFILL") == "1":
        backfill_ads(token(), int(os.environ.get("ADS_BACKFILL_N") or 40))
        return 0
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    now = dt.datetime.now(ET)
    today = now.date()
    daily = int(os.environ.get("BLOGGER_DAILY") or 40)
    per_run = int(os.environ.get("BLOGGER_PER_RUN") or 3)
    gap = int(os.environ.get("BLOGGER_GAP") or 60)
    days = int(os.environ.get("BLOGGER_DAYS") or 3650)
    done_today = sum(1 for v in state.values() if str(v.get("at", ""))[:10] == today.isoformat())
    want = (os.environ.get("SLUG") or "").strip()
    cands = []
    for p in sorted(REPORTS.glob("*.md")):
        slug = p.stem
        if (slug in state and not (os.environ.get("UPDATE") == "1" and slug == want)) or (want and slug != want):
            continue
        fm = front(p)
        if not fm or fm.get("draft"):
            continue
        try:
            d = dt.date.fromisoformat(str(fm.get("date"))[:10])
        except ValueError:
            continue
        if d > today or (not want and (today - d).days > days):
            continue
        # v2.9 2.5③(11-02 LAES·RZLV): 새 리포트는 영상(youtube_id)이 연결된 뒤 올린다 — 영상 전에 자동 게시돼 임베드가 빠졌다.
        # 이틀이 지나도 영상이 없으면 영상 없이 올린다(영상 없는 옛 리포트·글만 있는 회차).
        if not want and len(str(fm.get("youtube_id") or "").strip()) != 11 and (today - d).days < 2:
            print(f"{slug}: 영상 연결 전이라 미룸(youtube_id 없음)")
            continue
        cands.append((d, slug, fm))
    cands.sort(reverse=True)  # 최신 먼저
    room = 1 if want else min(per_run, max(0, daily - done_today))
    if not cands or room == 0:
        print(f"올릴 글 없음(후보 {len(cands)}, 오늘 {done_today}/{daily})")
        return 0
    dry = os.environ.get("DRY") == "1"
    tok = None if dry else token()
    n = 0
    for d, slug, fm in cands:
        if n >= room:
            break
        if not dry and not live(slug):
            print(f"{slug}: 아직 사이트에 안 열림, 건너뜀")
            continue
        title = short_title(fm)
        labels = [x for x in [str(fm.get("ticker") or ""), *related(fm), str(fm.get("theme") or ""), "미국주식"] if x]
        content = body(slug, fm)
        if dry:
            print(f"::notice title=미리보기 {slug}::{title} | 주소 {slug_en(slug, fm).replace(' ', '-')} | 라벨 {', '.join(labels)} | {html.unescape(content).replace(chr(10), " ")[:500]}")
            n += 1
            continue
        if n:
            time.sleep(gap)
        try:
            if os.environ.get("UPDATE") == "1" and slug in state:
                url = update(tok, state[slug]["url"], title, content, labels)
                state[slug]["updated"] = dt.datetime.now(ET).isoformat(timespec="minutes")
                print(f"::notice title=블로거 갱신::{slug} → {url}")
                n += 1
                continue
            url = publish(tok, title, content, labels, slug_en(slug, fm))
        except urllib.error.HTTPError as ex:
            if ex.code in (403, 429):  # 구글 게시 한도: 기록은 남기고 다음 실행에서 이어 간다
                msg = ex.read().decode("utf-8", "replace")[:300].replace("\n", " ")
                print(f"::warning title=블로거 한도 {ex.code}::{slug} 에서 멈춤, 이번 실행 {n}건 · {msg}")
                break
            raise
        state[slug] = {"url": url, "at": dt.datetime.now(ET).isoformat(timespec="minutes")}
        print(f"::notice title=블로거 게시::{slug} → {url}")
        n += 1
    if not dry:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:  # 로그를 못 보는 환경에서도 원인이 보이게 주석(annotation)으로 남긴다(응답 본문에는 비밀값이 없다)
        msg = e.read().decode("utf-8", "replace")[:600].replace("\n", " ")
        print(f"::error title=블로거 HTTP {e.code}::{e.url.split('?')[0]} {msg}")
        sys.exit(1)
