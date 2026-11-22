# 김박사 월드 브랜드 인트로·엔드카드(운영자 지시 2026-11-22 "인트로 영상을 만들어서 브랜드를 각인하고 아웃트로 영상도 넣어서 홍보장으로 활용")
# - 인트로: brand/intro.mp4(2.4초, 목소리 없음, 워드마크 + 정체성 한 줄) — 모든 롱폼에 같은 그림. make_slide_video.py가 **영상 맨 앞(0초)**에 놓고
#   (운영자 2026-11-22 "인트로로 브랜드를 각인하라고 했잖아" — 첫 훅 문단 뒤 15초대 스팅은 인트로로 인식되지 않음), 음성 앞에도 같은 길이를 비워
#   소리 로고(sfx.logo)를 넣는다(나레이션 전체가 2.4초 밀림 → slides_out/timing_video.json, segments.json 'brand_intro' = [0, 2.4]).
#   회차 질문 한 줄(intro_question: deck "intro_q" > 제목의 매매 질문 부분 — '○○ 지금 사도 될까?'·'○○ 지금 팔아야 될까?'·'○○ 실적 전에 살까, 뒤에 살까?' 등 미디어 skill/runbooks/angles.md 목록, '?'로 끝나는 첫 마디)이 있으면 intro.html을 그 줄과 함께 다시 찍는다(길이 같음, 브랜드가 주인공).
#   예전처럼 훅 뒤에 끼우려면 deck "brand_intro_para": 문단 번호(1~끝에서 두 번째) 또는 "hook"(시작 15초 이상인 첫 문단)
# - 엔드카드: outro 슬라이드 자리. 왼쪽 열에 워드마크·정체성 한 줄·홍보 칸 2개, 오른쪽은 유튜브 최종 화면 요소 자리(지침 A10)
#   홍보 칸: ① 그 회차 영양제 중간광고 코드(H1~H3)의 건강 가이드(설명란 둘째 줄과 같은 말) ② 회차마다 돌리는 칸(성적표·실시간 알림·김박사 몰)
#   slides.json "outro_promo": ["health"|"scorecard"|"alert"|"mall"|{tag,title,sub,url,note}] 로 직접 고른다(없으면 자동, []면 홍보 칸 없음)
# 사용: python3 brand.py build                 → brand/intro.mp4·brand/logo.wav 다시 만들기(디자인을 바꿀 때만, 결과를 커밋)
#       python3 brand.py endcard slides.json 출력.png  → 그 덱의 엔드카드 미리보기(고른 칸·검사 결과 출력)
import os, re, sys, json, hashlib, subprocess, datetime as dt
KIT = os.path.dirname(os.path.abspath(__file__)); BD = os.path.join(KIT, 'brand')
INTRO = os.path.join(BD, 'intro.mp4'); FPS = 30
IDENTITY = '통섭으로 읽는 주가 패턴'  # SKILL '채널 정체성: 하나의 통섭 마스터마인드'를 짧게
HEALTH = {'H1': ('오메가3', 'omega3'), 'H2': ('루테인', 'lutein'), 'H3': ('유산균', 'probiotics')}
PROMOS = {
    'scorecard': {'tag': '예측 성적표', 'title': '판정일마다 공개 채점', 'sub': '맞힌 것도 틀린 것도 그대로', 'url': 'drkimworld.com/scorecard', 'color': '#4FA3FF'},
    'alert': {'tag': '실시간 알림', 'title': '새 리포트 알림 참여', 'sub': '텔레그램과 인스타그램 김박사 월드', 'url': 't.me/drkimworld', 'color': '#5EC8FF'},
    'mall': {'tag': '김박사 몰', 'title': '쿠팡 장보기 입구', 'sub': '같은 가격, 채널 운영에 도움', 'url': 'drkimworld.com/mall', 'note': '쿠팡 파트너스 수수료', 'color': '#F5B83D'},
}
ROTATE = ['scorecard', 'alert', 'mall']
# 공개 문구 금지(SKILL 5장·midroll_check 거짓 긴급성·health.yaml): 가입·베팅·투자 권유·수익 암시·긴급성·보유·AI·효능 단정, 꺾쇠
BAN = re.compile(r'가입|회원|베팅|배팅|도박|추천주|매수|매도|수익|대박|급등|보장|무조건|지금 바로|오늘만|오늘까지|마감|임박|한정|선착순|놓치|마지막 기회|품절|'
                 r'AI|인공지능|보유|치료|완치|특효|처방|[<>]')


def health_code(deck):
    """그 회차 영양제 중간광고 코드: deck "health" > 쿠팡 카드 파일 이름(h1_card.png) > 쇼츠 띠 문구의 성분 이름"""
    c = str(deck.get('health') or '').upper()
    if c in HEALTH: return c
    m = re.search(r'(?:^|[/_\-])h([123])[_\-.]', os.path.basename(str(deck.get('shop') or '')).lower())
    if m: return 'H' + m.group(1)
    txt = str(deck.get('shop_strip') or '')
    for k, (nm, _) in HEALTH.items():
        if nm in txt: return k
    return None


def health_card(code):
    nm, slug = HEALTH[code]
    return {'tag': '건강 가이드', 'title': f'{nm} 고르는 법', 'sub': '설명란 둘째 줄 링크', 'url': f'health.drkimworld.com/guide/{slug}', 'note': '유료 광고 포함', 'color': '#3DDC97'}


def problems(card):
    """홍보 칸 문구 검사(check_slides OUTRO_PROMO와 같은 기준). 빈 목록이면 통과"""
    bad = []
    for k, lim in (('tag', 8), ('title', 12), ('sub', 20), ('note', 12)):
        v = str(card.get(k) or '')
        if k in ('tag', 'title') and not v: bad.append(f'{k} 없음')
        if len(v) > lim: bad.append(f'{k} {len(v)}자 > {lim}자: {v}')
        if BAN.search(v): bad.append(f'{k} 금지 표현 "{BAN.search(v).group(0)}": {v}')
    u = str(card.get('url') or '')
    if u and (len(u) > 40 or not re.fullmatch(r'[a-z0-9.\-]+\.[a-z]{2,}(/[a-z0-9\-/]*)?', u)): bad.append(f'url은 도메인+경로만(https·?·utm 없이 40자 이하): {u}')
    return bad


def pick(deck, day=None):
    """엔드카드 홍보 칸(최대 2개)과 그 이름표. 자동: ① 영양제 코드가 있으면 건강 가이드 ② 날짜·종목으로 돌리는 칸
    (건강 가이드가 있는 회차는 김박사 몰을 고르지 않는다 — 설명란 몰 줄과 같은 회차에 두지 않는 health_midroll 3절 5번과 같은 이유)"""
    code = health_code(deck)
    if 'outro_promo' in deck:
        out = []
        for x in deck['outro_promo'] or []:
            if isinstance(x, dict): out.append(('custom', dict(x)))
            elif x == 'health': code and out.append((f'health:{code}', health_card(code)))
            elif x in PROMOS: out.append((x, dict(PROMOS[x])))
        return out[:2]
    day = day or str(deck.get('date') or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date())
    pool = [k for k in ROTATE if not (code and k == 'mall')]
    seed = dt.date.fromisoformat(day[:10]).toordinal() + sum(ord(c) for c in str(deck.get('ticker', '')))
    out = [(f'health:{code}', health_card(code))] if code else []
    i = seed % len(pool)
    while len(out) < 2:
        k = pool[i % len(pool)]; i += 1
        if all(k != o[0] for o in out): out.append((k, dict(PROMOS[k])))
    return out


async def render_endcard(pw, cards, outdir, sec=0.7, gl_args=None):
    """엔드카드 등장 프레임(0.7초)을 찍어 목록으로. 글자 넘침·왼쪽 열 밖이면 BRAND_FAIL로 멈춘다"""
    os.makedirs(outdir, exist_ok=True)
    br = await pw.chromium.launch(args=gl_args or [])
    pg = await br.new_page(viewport={'width': 1920, 'height': 1080})
    await pg.goto('file://' + os.path.join(BD, 'endcard.html')); await pg.wait_for_timeout(200)
    await pg.evaluate('d=>render(d)', {'identity': IDENTITY, 'cards': cards})
    await pg.wait_for_timeout(80)
    m = await pg.evaluate('()=>measure()')
    bad = ([f'왼쪽 열이 화면 아래로 넘침(bottom {m["bottom"]:.0f} > 1000)'] if m['bottom'] > 1000 else []) + [f'넘침: {x}' for x in m['over']] + [f'두 줄로 꺾임: {x}' for x in m['lines']]
    if bad:
        await br.close(); sys.exit('BRAND_FAIL 엔드카드 ' + ' / '.join(bad))
    fr = []
    n = int(round(sec * FPS))
    for i in range(n + 1):
        await pg.evaluate('t=>at(t)', i / FPS); f = os.path.join(outdir, f'e{i:02d}.png')
        await pg.screenshot(path=f); fr.append(f)
    await br.close()
    return fr


Q_MAX = 28  # 질문 줄 글자 수 상한(46px 한 줄, 화면 폭 1400px 안)


_NAME = re.compile(r'[가-힣A-Za-z0-9&.\- ]{1,20}\([A-Z][A-Z0-9.]{0,5}\)')  # '블룸 에너지(BE)'


def _q_from_title(t):
    """제목에서 회차 질문 한 줄. 첫 '?'까지(예: '블룸 에너지(BE) 지금 사도 될까?', '아처 에비에이션(ACHR) 물타기 해도 될까?').
    질문 종류는 가리지 않는다(2026-11-22 매매 질문 회전, 미디어 skill/runbooks/angles.md). 첫 '?'까지가 Q_MAX자를 넘으면
    (사건 머리말 '어닝 쇼크 다음 날, 블룸 에너지(BE) 팔아야 될까?') 종목명(티커)부터, 없으면 마지막 ', '·' — ' 뒤부터 다시 잘라 본다.
    그래도 길거나 '?'가 없으면 None(긴 2지선다 질문은 slides.json "intro_q"에 줄인 질문을 직접 쓴다)"""
    t = str(t or '').strip().replace('？', '?'); i = t.find('?')
    q = t[:i + 1].strip() if i > 0 else ''
    if not q: return None
    if len(q) <= Q_MAX: return q
    cands = [m.group(0).strip() for m in _NAME.finditer(q)]
    for c in cands:
        r = q[q.index(c):]
        if len(r) <= Q_MAX: return r
    if cands: return None  # 종목명이 든 질문을 잘라 반쪽 질문('뒤에 살까?')을 띄우지 않는다 → deck "intro_q"로 직접
    for sep in (', ', ' — ', ' - '):
        if sep in q:
            r = q.rsplit(sep, 1)[1].strip()
            if 8 <= len(r) <= Q_MAX: return r
    return None


def intro_question(deck, base='.'):
    """인트로 화면 회차 질문 한 줄: deck "intro_q"(""/false면 없음) > 같은 폴더 mk_meta.py TITLE > upload_meta.json title.
    제목의 첫 '?'까지가 Q_MAX자 이하일 때만 쓴다(미스터리형 긴 제목은 질문 줄 없이 브랜드만)"""
    if 'intro_q' in deck:
        q = str(deck.get('intro_q') or '').strip()
        return q[:Q_MAX] if q else None
    mk = os.path.join(base, 'mk_meta.py')
    if os.path.exists(mk):
        m = re.search(r'^TITLE\s*=\s*[fr]?([\'"])(.+?)\1', open(mk, encoding='utf-8').read(), re.M)
        if m and _q_from_title(m.group(2)): return _q_from_title(m.group(2))
    um = os.path.join(base, 'upload_meta.json')
    if os.path.exists(um):
        try: return _q_from_title(json.load(open(um, encoding='utf-8')).get('title'))
        except (OSError, ValueError): pass
    return None


def intro_frames(outdir, q=None):
    """인트로 프레임 PNG 목록(72장 = 2.4초). 질문 줄이 없으면 brand/intro.mp4를 그대로 푼다(매 회차 같은 그림 — 각인),
    있으면 intro.html을 그 줄과 함께 1/30초씩 다시 찍는다(워드마크·정체성·움직임은 intro.mp4와 같음). 질문 줄이 넘치면 BRAND_FAIL"""
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith('.png'): os.remove(os.path.join(outdir, f))
    if not q:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', INTRO, '-vf', 'scale=1920:1080,fps=30', os.path.join(outdir, 'i%03d.png')], check=True)
    else:
        # 문구 검사는 하지 않는다: 그 회차 제목(V4 제목 검사를 이미 통과)의 앞부분이고, 회사 이름에 'AI' 같은 BAN 낱말이 들어갈 수 있다
        from playwright.sync_api import sync_playwright
        n = 72
        with sync_playwright() as p:
            br = p.chromium.launch(); pg = br.new_page(viewport={'width': 1920, 'height': 1080})
            pg.goto('file://' + os.path.join(BD, 'intro.html')); pg.wait_for_timeout(300)
            w = pg.evaluate('q=>setQ(q)', q)
            if w > 1400: br.close(); sys.exit(f'BRAND_FAIL 인트로 질문 줄이 넘침({w:.0f}px > 1400): {q}')
            for i in range(n):
                pg.evaluate('t=>frame(t)', i / FPS); pg.screenshot(path=os.path.join(outdir, f'i{i + 1:03d}.png'))
            br.close()
    return sorted(os.path.join(outdir, f) for f in os.listdir(outdir) if f.endswith('.png'))


def build():
    """intro.html을 1/30초씩 찍어 intro.mp4(소리 로고 포함)와 logo.wav를 만든다"""
    import asyncio, tempfile
    sys.path.insert(0, KIT); import sfx
    from playwright.async_api import async_playwright
    tmp = tempfile.mkdtemp(prefix='brand_')
    n = 72  # 2.4초 = sfx.logo 길이
    async def go():
        async with async_playwright() as p:
            br = await p.chromium.launch(); pg = await br.new_page(viewport={'width': 1920, 'height': 1080})
            await pg.goto('file://' + os.path.join(BD, 'intro.html')); await pg.wait_for_timeout(300)
            for i in range(n):
                await pg.evaluate('t=>frame(t)', i / FPS); await pg.screenshot(path=os.path.join(tmp, f'f{i:03d}.png'))
            await br.close()
    asyncio.run(go())
    wav = os.path.join(BD, 'logo.wav'); sfx.write_wav(wav, sfx.logo() * 0.9)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(FPS), '-i', os.path.join(tmp, 'f%03d.png'), '-i', wav, '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
                    '-pix_fmt', 'yuv420p', '-r', str(FPS), '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', INTRO], check=True)
    print('saved', INTRO, wav, f'{n} 프레임 {n / FPS:.1f}초')


if __name__ == '__main__':
    if sys.argv[1:2] == ['build']: build()
    elif sys.argv[1:2] == ['endcard']:
        import asyncio
        from playwright.async_api import async_playwright
        deck = json.load(open(sys.argv[2], encoding='utf-8')); ch = pick(deck)
        for k, c in ch: print(k, c['title'], c.get('url', ''), problems(c) or 'OK')
        async def go():
            async with async_playwright() as p:
                return await render_endcard(p, [c for _, c in ch], os.path.join(os.path.dirname(os.path.abspath(sys.argv[3])), 'endcard_frames'))
        fr = asyncio.run(go()); import shutil; shutil.copy(fr[-1], sys.argv[3]); print('saved', sys.argv[3])
    else: print(__doc__ or open(__file__).read().split('\nimport')[0])
