"""리포트 본문에 그림(피겨)을 자동으로 넣는다(2026-10-14, 이해를 돕고 중간 이탈을 줄이기 위해).

원고(마크다운)는 그대로 두고, 리포트 공통 구조(김박사 월드 리포트 틀)에서 숫자를 읽어 그림을 만든다.
읽지 못한 부분은 그림 없이 넘어간다(빌드를 막지 않음).

그림 종류(모두 HTML+CSS, 화면 폭에 맞춰 줄어들고 글자로도 값이 보인다. 상승 빨강 ▲ · 하락 파랑 ▼, 한국 시장 관례):
  1. 같은 뉴스, 정반대 반응 → 두 숫자 맞대기(첫머리 고리)
  2. 1.2 주가를 움직이는 변수 → 변수별 대표 반응 막대
  3. 2부 연대기 → 시기 흐름 띠(가장 최근 시기 '지금')
  4. 3부 이벤트 카드 → 사건별 당일 반응 막대(누르면 그 카드로), '같은 호재인데 왜 반응이 달랐나' → 짝 비교
  5. 4부 패턴 → 패턴별 사례 수·평균 당일 반응(카드에서 계산)
  6. 5.1 국면 → 세 국면 순환도와 '지금 여기'
"""
from __future__ import annotations

import html
import re

TAG = re.compile(r"<[^>]+>")
# 방향이 붙은 퍼센트: "4.3% 떨어졌다", "하루 50.2%, 닷새 동안 84.3% 올랐다"는 첫 숫자에 방향이 늦게 붙으므로 아래에서 따로 처리
DIR_PCT = re.compile(r"(\d+(?:\.\d+)?)%\s*(?:가량|정도|씩|이나|나|만큼)?\s*(올|오르|오른|상승|높|뛰|급등|반등|떨어|하락|내리|내린|내려|내렸|낮|빠|급락|밀)")
SIGNED_PCT = re.compile(r"(?:하루|당일|다음 날|다음날|다음 거래일)\s*([+\-−–]\d+(?:\.\d+)?)%")
UP_WORDS = ("올", "오르", "오른", "상승", "높", "뛰", "급등", "반등")


def _txt(s: str) -> str:
    return html.unescape(TAG.sub("", s)).strip()


def day_move(text: str) -> float | None:
    """'주가 반응' 같은 글에서 당일(첫) 반응 %를 부호와 함께 읽는다. 못 읽으면 None."""
    t = _txt(text)
    # '주가는/가격은 …' 이 나오면 그 뒤만 본다(앞의 '발작 77~81% 감소' 같은 다른 숫자를 주가로 읽지 않게)
    k = t.find("주가")
    if k < 0:
        k = max(t.find("가격은"), t.find("가격이"))
    if k > 0:
        t = t[k:]
    m = SIGNED_PCT.search(t)
    if m:
        return float(m.group(1).replace("−", "-").replace("–", "-"))
    # "하루 50.2%, 닷새 동안 84.3% 올랐다": 첫 숫자 뒤에 방향이 없으면, 그 문장의 첫 방향 단어를 쓴다
    first = re.search(r"(\d+(?:\.\d+)?)%", t)
    if not first:
        return 0.0 if "보합" in t else None
    if "보합" in t[: first.start()]:
        return 0.0
    # 장중 숫자는 건너뛰고 종가(마감) 숫자를 쓴다: "장중 10.9% 올라 …, 4.2% 오른 4.22달러로 마감"
    cands = [m for m in DIR_PCT.finditer(t) if "장중" not in t[max(0, m.start() - 6):m.start()]]
    m = cands[0] if cands else None
    if m and "장중" in t[max(0, first.start() - 6):first.start()]:
        return float(m.group(1)) * (1 if m.group(2).startswith(UP_WORDS) else -1)
    if m and m.start() == first.start():
        return float(m.group(1)) * (1 if m.group(2).startswith(UP_WORDS) else -1)
    sent_end = re.search(r"[.。]\s|$", t[first.end():])
    sent = t[first.end(): first.end() + (sent_end.start() if sent_end else len(t))]
    dm = re.search(r"(올|오르|오른|상승|높|뛰|급등|반등|떨어|하락|내리|내린|내려|내렸|낮|빠|급락|밀)", sent)
    if not dm:
        return None
    return float(first.group(1)) * (1 if dm.group(1).startswith(UP_WORDS) else -1)


def _fmt(v: float) -> str:
    if v == 0:
        return "보합"
    return f"{'+' if v > 0 else '−'}{round(abs(v), 2):g}%"


def _sign_cls(v: float) -> str:
    return "up" if v > 0 else "down" if v < 0 else "flat"


def bars(title: str, rows: list[dict], note: str = "", cls: str = "") -> str:
    """가운데 0에서 좌(하락)·우(상승)로 뻗는 막대 목록. rows: {label, sub?, value, href?, extra?}"""
    rows = [r for r in rows if r.get("value") is not None]
    if len(rows) < 2:
        return ""
    mx = max(abs(r["value"]) for r in rows) or 1
    out = [f'<figure class="kfig kfig-bars {cls}" role="group" aria-label="{html.escape(title)}">',
           f'<figcaption class="kfig-t">{html.escape(title)}</figcaption>',
           '<div class="kfig-legend" aria-hidden="true"><span class="kf-down">▼ 하락</span><span class="kf-up">상승 ▲</span></div>',
           '<ol class="kfb">']
    for r in rows:
        v = r["value"]; w = max(2.0, abs(v) / mx * 100)
        tag = "a" if r.get("href") else "div"
        href = f' href="{html.escape(r["href"])}"' if r.get("href") else ""
        sub = f'<span class="kfb-sub">{html.escape(r["sub"])}</span>' if r.get("sub") else ""
        extra = f'<span class="kfb-x">{html.escape(r["extra"])}</span>' if r.get("extra") else ""
        out.append(
            f'<li class="kfb-row {_sign_cls(v)}"><{tag} class="kfb-in"{href}>'
            f'<span class="kfb-l"><span class="kfb-name">{html.escape(r["label"])}</span>{sub}</span>'
            f'<span class="kfb-track"><span class="kfb-half kfb-neg">{f"<i style=\"width:{w:.1f}%\"></i>" if v < 0 else ""}</span>'
            f'<span class="kfb-half kfb-pos">{f"<i style=\"width:{w:.1f}%\"></i>" if v > 0 else ""}</span></span>'
            f'<span class="kfb-v">{"▲ " if v > 0 else "▼ " if v < 0 else ""}{_fmt(v)}{extra}</span></{tag}></li>')
    out.append("</ol>")
    if note:
        out.append(f'<p class="kfig-note">{html.escape(note)}</p>')
    out.append("</figure>")
    return "".join(out)


# ---------- 구간 나누기 ----------
def _h2s(body: str):
    return [(m.start(), m.end(), m.group(2) or "", _txt(m.group(3))) for m in re.finditer(r'<h2( id="([^"]*)")?>(.*?)</h2>', body, flags=re.S)]


def _section(body: str, pred):
    secs = _h2s(body)
    for i, (st, en, sid, t) in enumerate(secs):
        if pred(t):
            return en, (secs[i + 1][0] if i + 1 < len(secs) else len(body)), sid
    return None


def _after_core(body: str, start: int, end: int) -> int:
    """구간 첫 '핵심' 문단 바로 뒤(없으면 제목 바로 뒤)."""
    m = re.search(r"<p><strong>핵심</strong>.*?</p>", body[start:end], flags=re.S)
    return start + m.end() if m else start


# ---------- 1. 같은 뉴스, 정반대 반응 ----------
def fig_hook(body: str):
    s = _section(body, lambda t: t.startswith("같은 뉴스"))
    if not s:
        return None
    st, en, _ = s
    tiles, year = [], ""
    for pm in re.finditer(r"<p>(.*?)</p>", body[st:en], flags=re.S):
        t = _txt(pm.group(1))
        dm = re.search(r"(?:(\d{4})년\s*)?(\d{1,2})월\s*(\d{1,2})일", t)
        k = max(t.find("주가"), t.find("가격"))
        v = day_move(t[k:] if k >= 0 else t)
        if dm and v is not None:
            year = dm.group(1) or year
            what = re.split(r"[,(]| 결과| 발표| 소식", t[dm.end():].lstrip(" ,").strip())[0].strip()
            tiles.append((f"{year + '.' if year else ''}{int(dm.group(2)):02d}.{int(dm.group(3)):02d}", what[:24], v))
        if len(tiles) == 2:
            break
    if len(tiles) < 2 or (tiles[0][2] > 0) == (tiles[1][2] > 0):
        return None
    parts = ['<figure class="kfig kfig-hook" role="group" aria-label="같은 뉴스, 정반대 반응"><div class="kfh">']
    for i, (d, what, v) in enumerate(tiles):
        if i:
            parts.append('<span class="kfh-vs" aria-hidden="true">vs</span>')
        parts.append(f'<div class="kfh-tile {_sign_cls(v)}"><span class="kfh-d">{html.escape(d)}</span>'
                     f'<strong class="kfh-v">{"▲" if v > 0 else "▼"} {_fmt(v)}</strong><span class="kfh-w">{html.escape(what)}</span></div>')
    noun = "주가는" if "주가" in body[st:en] else "가격은"   # 코인 리포트는 '가격'
    parts.append(f'</div><figcaption class="kfig-note">같은 소식인데 {noun} 반대로 움직였다. 무엇이 갈랐는지는 3부·4부에서.</figcaption></figure>')
    # 두 번째 문단 뒤에 넣는다
    ps = list(re.finditer(r"</p>", body[st:en]))
    at = st + (ps[1].end() if len(ps) >= 2 else 0)
    return at, "".join(parts)


# ---------- 2. 1.2 주가를 움직이는 변수 ----------
def fig_drivers(body: str):
    m = re.search(r'<h3[^>]*>\s*1\.2[^<]*</h3>', body)
    if not m:
        return None
    nxt = re.search(r"<h[23][\s>]", body[m.end():])
    end = m.end() + (nxt.start() if nxt else len(body) - m.end())
    sec = body[m.end():end]
    rows = []
    for dm in re.finditer(r"<p><strong>(.*?)</strong>(.*?)</p>(\s*<ul>(.*?)</ul>)?", sec, flags=re.S):
        name = _txt(dm.group(1))
        rest = _txt(dm.group(2))
        ex = _txt(dm.group(4) or "") or (rest[rest.find("예:"):] if "예:" in rest else "")
        if not ex:
            continue
        v = day_move(ex)
        date = re.search(r"(\d{4})년 (\d{1,2})월(?: (\d{1,2})일)?", ex)
        sub = f"{date.group(1)}.{int(date.group(2)):02d}" + (f".{int(date.group(3)):02d}" if date.group(3) else "") if date else ""
        if v is not None and sub and len(name) <= 30:  # 날짜가 있는 하루짜리 사례만(몇 달 누적 하락은 빼기)
            rows.append({"label": name, "sub": sub, "value": v})
    out = bars("변수별 대표 사례의 하루 주가 반응", rows, "각 변수의 예로 든 사건 하루 동안의 주가 변화", "kfig-drivers")
    return (m.end(), out) if out else None


# ---------- 3. 2부 연대기 ----------
def fig_timeline(body: str):
    s = _section(body, lambda t: bool(re.match(r"2부", t)))
    if not s:
        return None
    st, en, _ = s
    items = []
    for hm in re.finditer(r'<h3( id="([^"]*)")?>(.*?)</h3>', body[st:en], flags=re.S):
        t = _txt(hm.group(3))
        pm = re.match(r"시기\s*(\d+)\s*[·:.\-]\s*(.*?)\s*(?:\(([^)]*)\))?\s*$", t)
        if pm:
            items.append((pm.group(1), pm.group(2), pm.group(3) or "", hm.group(2) or ""))
    if len(items) < 3:
        return None
    out = ['<figure class="kfig kfig-time" role="group" aria-label="연대기 한눈에"><figcaption class="kfig-t">시기 흐름 한눈에</figcaption><ol class="kft">']
    for i, (n, name, rng, hid) in enumerate(items):
        now = i == len(items) - 1
        a = f'<a class="kft-in" href="#{html.escape(hid)}">' if hid else '<span class="kft-in">'
        z = "</a>" if hid else "</span>"
        out.append(f'<li class="kft-i{" now" if now else ""}">{a}<span class="kft-n">{html.escape(n)}</span>'
                   f'<span class="kft-r">{html.escape(rng)}{" · 지금" if now else ""}</span><span class="kft-name">{html.escape(name)}</span>{z}</li>')
    out.append('</ol><p class="kfig-note">시기를 누르면 그 이야기로 갑니다.</p></figure>')
    return _after_core(body, st, en), "".join(out)


# ---------- 4. 3부 이벤트 카드 ----------
CARD_RE = re.compile(r"<p><strong>(\d{4}\.\d{1,2}(?:\.\d{1,2})?(?:~[\d.]+)?)\s*·\s*(.*?)</strong></p>\s*<ul>(.*?)</ul>", re.S)


def event_cards(body: str) -> list[dict]:
    s = _section(body, lambda t: "이벤트 카드" in t)
    if not s:
        return []
    st, en, _ = s
    cards = []
    for cm in CARD_RE.finditer(body, st, en):
        title = _txt(cm.group(2))
        pats = re.findall(r"P(\d+)", (re.search(r"\(([^()]*P\d[^()]*)\)\s*$", title) or [None, ""])[1])
        clean = re.sub(r"\s*\([^()]*P\d[^()]*\)\s*$", "", title)
        react = re.search(r"<li>\s*(?:<strong>)?\s*(?:주가|가격|주식) 반응\s*(?:</strong>)?\s*:?(.*?)</li>", cm.group(3), flags=re.S)
        v = day_move(react.group(1)) if react else None
        cards.append({"date": cm.group(1), "title": clean, "pats": [f"P{p}" for p in pats], "value": v,
                      "pos": cm.start(), "end": cm.end()})
    return cards


def fig_events(body: str, cards: list[dict]):
    s = _section(body, lambda t: "이벤트 카드" in t)
    if not s or len([c for c in cards if c["value"] is not None]) < 4:
        return None
    st, en, _ = s
    rows = []
    for i, c in enumerate(cards):
        if c["value"] is None:
            continue
        short = c["title"] if len(c["title"]) <= 26 else c["title"][:25].rstrip(" ,·") + "…"
        rows.append({"label": short, "sub": c["date"] + (" · " + ",".join(c["pats"]) if c["pats"] else ""), "value": c["value"], "href": f"#ev-{i + 1}"})
    out = bars(f"사건 {len(rows)}개, 직후 주가 반응", rows, "최신 사건부터. 숫자는 각 카드의 첫 반응(대부분 당일 종가 기준). 줄을 누르면 그 사건 카드로 갑니다.", "kfig-events")
    return (_after_core(body, st, en), out) if out else None


def fig_pairs(body: str):
    m = re.search(r'<h3[^>]*>[^<]*(?:같은 호재|같은 소식)[^<]*</h3>', body)
    if not m:
        return None
    nxt = re.search(r"<h[23][\s>]", body[m.end():])
    end = m.end() + (nxt.start() if nxt else len(body) - m.end())
    groups = []
    for gm in re.finditer(r"<p><strong>(.*?)</strong></p>\s*<ul>(.*?)</ul>", body[m.end():end], flags=re.S):
        items = []
        title = _txt(gm.group(1))
        tv = re.findall(r"([^()·]+?)\s*\(([+\-−–]\d+(?:\.\d+)?)%\)", title)
        if len(tv) < 2:  # '사례 쌍 ① 주식 판매 소식: 2026.06.11 +9.62% vs 2026.06.23 -24.64%'
            tv = re.findall(r"(\d{4}\.\d{1,2}\.\d{1,2})[^+\-−–\d]*?([+\-−–]\d+(?:\.\d+)?)%", title)
        if len(tv) >= 2:  # '사례 쌍 1 · 1분기 실적(-6.93%)과 2분기 실적(+29.45%)'
            items = [{"label": re.sub(r"^(과|와|및|그리고|,)\s*", "", lab.strip()), "value": float(v.replace("−", "-").replace("–", "-"))} for lab, v in tv[:2]]
            name = title.split("·")[0].strip() if "·" in title else re.split(r":|\d{4}\.", title)[0].strip(" :")
            groups.append((name, items))
            continue
        for li in re.findall(r"<li>(.*?)</li>", gm.group(2), flags=re.S):
            t = _txt(li)
            lab = t.split(":")[0].strip() if ":" in t else t[:20]
            v = day_move(t.split(":", 1)[1] if ":" in t else t)
            if v is not None:
                items.append({"label": lab, "value": v})
        if len(items) >= 2:
            groups.append((_txt(gm.group(1)), items[:2]))
    if not groups:
        return None
    mx = max(abs(x["value"]) for _, its in groups for x in its) or 1
    out = ['<figure class="kfig kfig-pairs" role="group" aria-label="같은 호재, 다른 반응"><figcaption class="kfig-t">같은 호재, 다른 반응</figcaption>']
    for name, its in groups:
        out.append(f'<div class="kfp"><p class="kfp-name">{html.escape(name)}</p><ol class="kfb">')
        for x in its:
            v = x["value"]; w = max(2.0, abs(v) / mx * 100)
            out.append(f'<li class="kfb-row {_sign_cls(v)}"><div class="kfb-in"><span class="kfb-l"><span class="kfb-name">{html.escape(x["label"])}</span></span>'
                       f'<span class="kfb-track"><span class="kfb-half kfb-neg">{f"<i style=\"width:{w:.1f}%\"></i>" if v < 0 else ""}</span>'
                       f'<span class="kfb-half kfb-pos">{f"<i style=\"width:{w:.1f}%\"></i>" if v > 0 else ""}</span></span>'
                       f'<span class="kfb-v">{"▲ " if v > 0 else "▼ " if v < 0 else ""}{_fmt(v)}</span></div></li>')
        out.append("</ol></div>")
    out.append("</figure>")
    return m.end(), "".join(out)


# ---------- 5. 4부 패턴 ----------
def fig_patterns(body: str, cards: list[dict]):
    """패턴마다 그 패턴이 붙은 사건 카드의 반응을 점으로(평균은 한 카드에 패턴이 여럿 붙으면 오해를 부르므로 점 전부 + 중앙값)."""
    s = _section(body, lambda t: bool(re.match(r"4부", t)))
    if not s:
        return None
    st, en, _ = s
    names = {}
    for hm in re.finditer(r"<h3[^>]*>\s*(P\d+)\.?\s+(.*?)</h3>", body[st:en], flags=re.S):
        names[hm.group(1)] = _txt(hm.group(2))
    rows = []
    for p, name in names.items():
        vs = sorted(c["value"] for c in cards if p in c["pats"] and c["value"] is not None)
        if vs:
            n = len(vs); med = vs[n // 2] if n % 2 else (vs[n // 2 - 1] + vs[n // 2]) / 2
            rows.append((p, name, vs, med))
    if len(rows) < 2:
        return None
    mx = max(abs(v) for _, _, vs, _ in rows for v in vs) or 1
    out = ['<figure class="kfig kfig-dots" role="group" aria-label="패턴별 사건 반응"><figcaption class="kfig-t">패턴별 사건 반응(점 하나 = 사건 하나)</figcaption>',
           '<div class="kfig-legend" aria-hidden="true"><span class="kf-down">▼ 하락</span><span class="kf-up">상승 ▲</span></div><ol class="kfb">']
    for p, name, vs, med in rows:
        dots = "".join(f'<i class="{_sign_cls(v)}" style="left:{50 + v / mx * 48:.1f}%" title="{_fmt(v)}"></i>' for v in vs)
        out.append(f'<li class="kfb-row {_sign_cls(med)}"><div class="kfb-in"><span class="kfb-l"><span class="kfb-name">{html.escape(p)}. {html.escape(name)}</span>'
                   f'<span class="kfb-sub">사례 {len(vs)}건</span></span><span class="kfd-track" aria-hidden="true"><b></b>{dots}</span>'
                   f'<span class="kfb-v">중앙 {_fmt(round(med, 2))}</span></div></li>')
    out.append('</ol><p class="kfig-note">3부 사건 카드에 붙은 패턴 번호로 모았다. 한 사건에 패턴이 둘 붙으면 두 줄 모두에 나온다. 사례가 적은 패턴은 참고만.</p></figure>')
    return _after_core(body, st, en), "".join(out)


# ---------- 6. 5.1 국면 ----------
def fig_phases(body: str):
    m = re.search(r'<h3[^>]*>\s*5\.1[^<]*</h3>', body)
    if not m:
        return None
    nxt = re.search(r"<h[23][\s>]", body[m.end():])
    end = m.end() + (nxt.start() if nxt else len(body) - m.end())
    sec = body[m.end():end]
    ph = []
    for pm in re.finditer(r"<p><strong>([^<]*?)</strong>[^<]*</p>\s*<ul>", sec, flags=re.S):
        t = _txt(pm.group(1))
        if "진단" in t:
            continue
        km = re.match(r"국면\s*([A-Z가-힣0-9])\s*[·:.\-]\s*(.*)$", t)
        if km:
            ph.append((km.group(1), km.group(2)))
        else:
            ph.append(("", re.sub(r"\s*(?:의)?\s*신호\s*\d*\s*개?$", "", t).strip()))
    if len(ph) < 2 or len(ph) > 5:
        return None
    dm = re.search(r"진단[^<:]*:\s*([^<]*)", sec) or re.search(r"<strong>[^<]*진단[^<:]*:\s*([^<]*)", body)
    diag = _txt(dm.group(1)) if dm else ""
    cur, when = "", diag
    for k, name in ph:
        core = re.sub(r"\s*단계$", "", name)
        if (k and re.search(r"국면\s*" + re.escape(k), diag)) or (core and core in diag):
            cur = k or name
            break
    ph = [(k or name, name if k else "") for k, name in ph]
    labels = {k: n for k, n in ph}
    out = ['<figure class="kfig kfig-phase" role="group" aria-label="국면 순환"><figcaption class="kfig-t">세 국면의 순환' + (" · 지금 위치" if cur else "") + '</figcaption><ol class="kfph">']
    for k, name in ph:
        on = k == cur
        head = f"국면 {k}" if name else k
        out.append(f'<li class="kfph-i{" now" if on else ""}"><span class="kfph-k">{html.escape(head)}</span>' + (f'<span class="kfph-n">{html.escape(name)}</span>' if name else "")
                   + (f'<span class="kfph-here">지금 여기{(" · " + html.escape(when)) if when else ""}</span>' if on else "") + "</li>")
    out.append('</ol><p class="kfig-note">국면은 화살표 방향으로 돌고, 마지막 국면 다음에는 다시 처음으로 돌아가곤 했다. 아래 신호로 지금 위치를 확인한다.</p></figure>')
    return m.end(), "".join(out)


def add_figures(body: str) -> tuple[str, int]:
    """본문 HTML에 그림을 넣고 (새 본문, 넣은 그림 수)를 돌려준다. 이벤트 카드에는 #ev-번호를 단다(그림에서 바로 가기)."""
    cards = event_cards(body)
    inserts = []
    for fn in (fig_hook, fig_drivers, fig_timeline, fig_pairs, fig_phases):
        try:
            r = fn(body)
        except Exception:
            r = None
        if r:
            inserts.append(r)
    for fn in (fig_events, fig_patterns):
        try:
            r = fn(body, cards)
        except Exception:
            r = None
        if r:
            inserts.append(r)
    # 카드 앵커(뒤에서부터 넣어 위치가 밀리지 않게)
    edits = [(c["pos"], c["pos"] + 2, f'<p id="ev-{i + 1}"') for i, c in enumerate(cards)]
    edits += [(at, at, "\n" + h + "\n") for at, h in inserts]
    for a, b, h in sorted(edits, key=lambda x: (x[0], x[1]), reverse=True):
        body = body[:a] + h + body[b:]
    return body, len(inserts)
