"""인스타그램 카드뉴스(캐러셀) 만들기 — 운영자 지시 2026-10-29 "인스타는 릴스 폐기하고 카드뉴스로 완전히 전환".

cards.json 한 파일로 1080×1350(4:5) JPEG 7~10장을 만든다. 잘 되는 금융 카드뉴스 계정들의 공통 구조를 따른다:
  1장 표지 = 피드에서 보이는 유일한 장 → 모순 숫자 둘 + 질문, 티커 칩, '넘겨 보기'
  2장 = 두 번째 훅(무슨 회사인지 한 줄 + 왜 지금인지)
  가운데 = 한 장에 생각 하나·큰 숫자 하나(본문 2~3문장)
  기록 장 = 'N번 중 M번' 점 그림(과거 패턴 결론은 카드에서 공개)
  시나리오 장 = 가능성 구간 + 댓글 번호 투표
  마지막 장 = 저장 유도 + 무료 리포트(프로필 링크 → 사이트 검색) + 면책
사용: python3 tools/cardnews/make_cards.py cards.json static/social/<slug>/   → card-01.jpg …, contact.jpg(검수용)

cards.json:
{"ticker":"IREN","name":"아이렌","total":9,
 "cards":[
  {"kind":"cover","kicker":"미국주식 미스터리","title":"차입금 3.6억 달러 빌린 날\n주가는 **+5.1%**","sub":"왜 올랐을까?","vs":[["대출","3.6억 달러"],["주가","+5.1%"]]},
  {"kind":"point","label":"단서 1 · 바닥","num":"$23.72","num_color":"red","caption":"10.26 장중 52주 최저","body":"..."},
  {"kind":"bars","label":"단서 2 · 업종","title":"10.27 하루 상승률","rows":[["네비우스",11.2],["사이퍼",10.0],["아이렌",7.9]]},
  {"kind":"record","label":"기록","title":"급락 묶음 뒤 스무 거래일","n":7,"m":7,"caption":"일곱 번 모두 더 낮았다"},
  {"kind":"scenarios","title":"11월 19일, 어느 쪽?","rows":[["1","반등이 스무 날 넘김","중간 20~30%"],...],"ask":"댓글에 번호 하나"},
  {"kind":"cta","title":"날짜별 기록표는\n무료 리포트에","items":["...","..."],"search":"아이렌","save":"저장해 두고 11월 5일 실적 때 다시 보기"}
 ]}
텍스트의 **굵게**는 강조색, 숫자 색은 green|red|amber|white.
"""
import html, json, os, re, sys

W, H = 1080, 1350
C = {"bg": "#0b1220", "card": "#111a2e", "line": "#1e2a44", "ink": "#f8fafc", "muted": "#94a3b8",
     "amber": "#f59e0b", "green": "#4ade80", "red": "#f87171", "white": "#f8fafc"}
LIMITS = {"title": 40, "body": 140, "caption": 30, "sub": 24, "label": 16}


def esc(s):
    s = html.escape(str(s))
    s = re.sub(r"\*\*(.+?)\*\*", r'<b class="hl">\1</b>', s)
    return s.replace("\n", "<br>")


def frame(inner, i, total, spec, last=False):
    swipe = "" if last else '<div class="swipe">넘겨 보기 →</div>'
    return f"""<div class="top"><span class="brand">김박사 월드</span><span class="pg">{esc(spec['ticker'])} · {i}/{total}</span></div>
<div class="body">{inner}</div>
<div class="bot"><span>@drkimworld</span>{swipe}</div>"""


def card_html(c, i, total, spec):
    k = c["kind"]
    if k == "cover":
        vs = ""
        if c.get("vs"):
            (l1, v1), (l2, v2) = c["vs"][:2]
            col = lambda v: C["green"] if str(v).startswith("+") else C["red"] if str(v)[:1] in "-−" else C["amber"]
            vs = f"""<div class="vs"><div class="vbox"><div class="vl">{esc(l1)}</div><div class="vv" style="color:{col(v1)}">{esc(v1)}</div></div>
<div class="vsx">vs</div><div class="vbox"><div class="vl">{esc(l2)}</div><div class="vv" style="color:{col(v2)}">{esc(v2)}</div></div></div>"""
        inner = f"""<div class="chip">{esc(spec['ticker'])}</div><div class="kicker">{esc(c.get('kicker', '미국주식 미스터리'))}</div>
<div class="ctitle">{esc(c['title'])}</div>{vs}<div class="csub">{esc(c.get('sub', ''))}</div>"""
    elif k == "point":
        inner = f"""<div class="label">{esc(c.get('label', ''))}</div><div class="num" style="color:{C.get(c.get('num_color', 'amber'))}">{esc(c['num'])}</div>
<div class="caption">{esc(c.get('caption', ''))}</div><div class="text">{esc(c.get('body', ''))}</div>"""
    elif k == "text":
        inner = f"""<div class="label">{esc(c.get('label', ''))}</div><div class="ttitle">{esc(c['title'])}</div><div class="text">{esc(c.get('body', ''))}</div>"""
    elif k == "bars":
        mx = max(abs(v) for _, v in c["rows"]) or 1
        rows = "".join(
            f"""<div class="brow{' me' if lab == spec['name'] else ''}"><div class="blab">{esc(lab)}</div><div class="btrack"><div class="bfill" style="width:{abs(v) / mx * 100:.0f}%;background:{C['green'] if v >= 0 else C['red']}"></div></div><div class="bval">{v:+.1f}%</div></div>"""
            for lab, v in c["rows"])
        inner = f"""<div class="label">{esc(c.get('label', ''))}</div><div class="ttitle">{esc(c['title'])}</div><div class="bars">{rows}</div><div class="text">{esc(c.get('body', ''))}</div>"""
    elif k == "record":
        dots = "".join(f'<span class="dot{" on" if j < c["m"] else ""}"></span>' for j in range(c["n"]))
        inner = f"""<div class="label">{esc(c.get('label', '기록'))}</div><div class="ttitle">{esc(c['title'])}</div>
<div class="big">{c['n']}번 중 <b class="hl">{c['m']}번</b></div><div class="dots">{dots}</div><div class="caption">{esc(c.get('caption', ''))}</div><div class="text">{esc(c.get('body', ''))}</div>"""
    elif k == "scenarios":
        rows = "".join(f"""<div class="srow"><div class="sno">{esc(n)}</div><div class="sname">{esc(t)}</div><div class="slv">{esc(lv)}</div></div>""" for n, t, lv in c["rows"])
        inner = f"""<div class="label">{esc(c.get('label', '앞으로'))}</div><div class="ttitle">{esc(c['title'])}</div><div class="srows">{rows}</div>
<div class="note">가능성은 과거 기록과 지금 신호로 매긴 추정 구간입니다</div><div class="ask">{esc(c.get('ask', '댓글에 번호 하나만 남겨 주세요'))}</div>"""
    elif k == "cta":
        items = "".join(f"<li>{esc(x)}</li>" for x in c.get("items", []))
        inner = f"""<div class="ttitle">{esc(c['title'])}</div><ul class="items">{items}</ul>
<div class="howto">프로필 링크 → <b>drkimworld.com</b><br>에서 <b class="hl">'{esc(c['search'])}'</b> 검색</div>
<div class="save">🔖 {esc(c.get('save', '저장해 두고 다시 보기'))}</div>
<div class="disc">공개 공시·시세를 정리한 교육용 자료이며 매수·매도 권유가 아닙니다</div>"""
    else:
        raise SystemExit(f"모르는 카드 종류: {k}")
    return frame(inner, i, total, spec, last=(k == "cta"))


CSS = f"""
@font-face {{ font-family: KR; src: local('Noto Sans CJK KR'), local('NotoSansCJKkr-Bold'); }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ width: {W}px; height: {H}px; background: {C['bg']}; color: {C['ink']}; font-family: 'Noto Sans CJK KR', 'Noto Sans KR', KR, sans-serif;
  word-break: keep-all; overflow: hidden; display: flex; flex-direction: column; padding: 64px 76px 56px; }}
.top {{ display: flex; justify-content: space-between; font-size: 30px; color: {C['muted']}; font-weight: 700; }}
.brand {{ color: {C['amber']}; }}
.body {{ flex: 1; display: flex; flex-direction: column; justify-content: center; }}
.bot {{ display: flex; justify-content: space-between; font-size: 28px; color: {C['muted']}; }}
.swipe {{ color: {C['amber']}; font-weight: 700; }}
.hl {{ color: {C['amber']}; }}
.chip {{ align-self: flex-start; background: {C['amber']}; color: {C['bg']}; font-weight: 900; font-size: 40px; padding: 6px 22px; border-radius: 14px; }}
.kicker {{ margin-top: 28px; font-size: 36px; color: {C['muted']}; font-weight: 700; }}
.ctitle {{ margin-top: 18px; font-size: 84px; line-height: 1.22; font-weight: 900; letter-spacing: -2px; }}
.csub {{ margin-top: 30px; font-size: 52px; font-weight: 800; color: {C['amber']}; }}
.vs {{ margin-top: 48px; display: flex; align-items: center; gap: 24px; }}
.vbox {{ flex: 1; background: {C['card']}; border: 3px solid {C['line']}; border-radius: 28px; padding: 26px 30px; }}
.vl {{ font-size: 32px; color: {C['muted']}; font-weight: 700; }}
.vv {{ font-size: 76px; font-weight: 900; letter-spacing: -2px; }}
.vsx {{ font-size: 34px; color: {C['muted']}; }}
.label {{ font-size: 34px; color: {C['amber']}; font-weight: 800; }}
.num {{ margin-top: 10px; font-size: 190px; font-weight: 900; letter-spacing: -6px; line-height: 1.05; }}
.caption {{ margin-top: 10px; font-size: 40px; color: {C['muted']}; font-weight: 700; }}
.text {{ margin-top: 44px; font-size: 44px; line-height: 1.55; font-weight: 500; }}
.ttitle {{ margin-top: 14px; font-size: 68px; line-height: 1.25; font-weight: 900; letter-spacing: -1px; }}
.bars {{ margin-top: 48px; display: flex; flex-direction: column; gap: 26px; }}
.brow {{ display: flex; align-items: center; gap: 22px; font-size: 40px; }}
.brow.me .blab, .brow.me .bval {{ color: {C['amber']}; font-weight: 900; }}
.blab {{ width: 250px; font-weight: 700; }}
.btrack {{ flex: 1; height: 46px; background: {C['card']}; border-radius: 12px; overflow: hidden; }}
.bfill {{ height: 100%; border-radius: 12px; }}
.bval {{ width: 150px; text-align: right; font-weight: 800; }}
.big {{ margin-top: 36px; font-size: 104px; font-weight: 900; letter-spacing: -3px; }}
.dots {{ margin-top: 26px; display: flex; flex-wrap: wrap; gap: 18px; }}
.dot {{ width: 74px; height: 74px; border-radius: 50%; border: 5px solid {C['line']}; }}
.dot.on {{ background: {C['red']}; border-color: {C['red']}; }}
.srows {{ margin-top: 36px; display: flex; flex-direction: column; gap: 20px; }}
.srow {{ display: flex; align-items: center; gap: 22px; background: {C['card']}; border: 3px solid {C['line']}; border-radius: 22px; padding: 22px 26px; }}
.sno {{ width: 64px; height: 64px; border-radius: 50%; background: {C['amber']}; color: {C['bg']}; font-size: 38px; font-weight: 900; display: flex; align-items: center; justify-content: center; flex: none; }}
.sname {{ flex: 1; font-size: 40px; font-weight: 800; }}
.slv {{ font-size: 32px; color: {C['muted']}; font-weight: 700; text-align: right; }}
.note {{ margin-top: 22px; font-size: 28px; color: {C['muted']}; }}
.ask {{ margin-top: 30px; font-size: 46px; font-weight: 900; color: {C['amber']}; }}
.items {{ margin-top: 40px; list-style: none; display: flex; flex-direction: column; gap: 18px; font-size: 42px; font-weight: 600; }}
.items li::before {{ content: '✓ '; color: {C['green']}; font-weight: 900; }}
.howto {{ margin-top: 48px; background: {C['card']}; border: 3px solid {C['amber']}; border-radius: 26px; padding: 30px 34px; font-size: 46px; line-height: 1.45; font-weight: 700; }}
.save {{ margin-top: 34px; font-size: 42px; font-weight: 800; }}
.disc {{ margin-top: 30px; font-size: 27px; color: {C['muted']}; }}
"""


def check(spec):
    bad = []
    cards = spec["cards"]
    if not 7 <= len(cards) <= 10: bad.append(f"카드 {len(cards)}장 — 7~10장")
    if cards[0]["kind"] != "cover": bad.append("1장은 cover")
    if cards[-1]["kind"] != "cta": bad.append("마지막 장은 cta(저장·리포트 안내)")
    if not any(c["kind"] == "record" for c in cards): bad.append("기록(N번 중 M번) 카드가 없음 — 과거 패턴 결론은 카드에서 공개")
    if not any(c["kind"] == "scenarios" for c in cards): bad.append("시나리오·투표 카드가 없음")
    for i, c in enumerate(cards, 1):
        for key, lim in LIMITS.items():
            v = str(c.get(key, "")).replace("**", "")
            if len(v) > lim: bad.append(f"{i}장 {key} {len(v)}자 > {lim}")
        if c["kind"] == "cover" and c["title"].count("\n") > 2: bad.append("표지 제목은 3줄 이하")
        blob = json.dumps(c, ensure_ascii=False)
        if "빚" in blob: bad.append(f"{i}장 '빚' 금지 → 부채·차입금(v2.1)")
        if re.search(r"\d\s*[만억조]\s*\$", blob): bad.append(f"{i}장 '억$' 혼합 표기 금지")
    return bad


def main(spec_path, out_dir):
    spec = json.load(open(spec_path, encoding="utf-8"))
    bad = check(spec)
    if bad:
        print("\n".join("CARD " + b for b in bad)); sys.exit(1)
    os.makedirs(out_dir, exist_ok=True)
    from playwright.sync_api import sync_playwright
    total = len(spec["cards"]); outs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        for i, c in enumerate(spec["cards"], 1):
            pg.set_content(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{card_html(c, i, total, spec)}</body></html>")
            pg.wait_for_timeout(150)
            # 넘침 검사: 본문이 화면 밖으로 나가면 실패
            over = pg.evaluate("document.body.scrollHeight > window.innerHeight + 2")
            if over: print(f"CARD {i}장 글이 넘침 — 줄이기"); sys.exit(1)
            out = os.path.join(out_dir, f"card-{i:02d}.jpg")
            pg.screenshot(path=out, type="jpeg", quality=92)
            outs.append(out)
        b.close()
    from PIL import Image
    th = [Image.open(o).resize((270, 338)) for o in outs]
    sheet = Image.new("RGB", (270 * min(5, len(th)), 338 * ((len(th) + 4) // 5)), "#000")
    for j, t in enumerate(th): sheet.paste(t, ((j % 5) * 270, (j // 5) * 338))
    sheet.save(os.path.join(out_dir, "contact.jpg"), quality=85)
    print(f"CARDS_OK {len(outs)}장 → {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
