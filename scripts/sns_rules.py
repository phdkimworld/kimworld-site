#!/usr/bin/env python3
"""SNS 대기열 글 규칙 검사(사이트 쪽 사본). sns-draft.yml 이 API 초안을 검사할 때 쓴다.

원본은 미디어 저장소 tools/queue_check.py(2026-11-27 기준)의 T20·S1·AD2·self_reply·기본 길이 검사다.
파일·폴더에 기대는 검사(릴스 표지 파일 크기, 카드뉴스 묶음, 같은 날 관찰 글, plain_check·macro_check 호출)와
publish_at 날짜로 규칙을 켜고 끄는 부분은 뺐다(초안은 언제나 새 회차라 모든 규칙을 켠다).
초안을 social/queue 로 옮긴 뒤에는 제작자가 미디어 tools/queue_check.py 전체를 다시 돌린다(이 사본은 그 부분집합).
원본 규칙이 바뀌면 이 파일도 같이 고친다.

사용(파이썬): problems(name, post, kind, source_text=None) → 문제 목록(빈 목록이면 통과)
  kind: th1 | th2 | observe | igreels | reels
"""
import re
from datetime import datetime, timedelta, timezone

DIV = re.compile(r'^\s*(?:[─━—–\-=·]{3,}|[─━—–\-]+\s*광고\s*[─━—–\-]+)\s*$')
WHO_S = r'분이라면|분들은|하시는 분|드시는 분|보시는 분|이라면|이시라면|신 분|날이 많다면|많으시다면'
SR_BAN = [(r'https?://|www\.|\.com\b|t\.me/', '링크'), (r'매수|매도|사세요|파세요|담으세요|줍줍|물타기|손절|익절|목표\s*(가|주가)', '매매 권유·목표가'),
          (r'수익\s*(보장|약속|확실)|확실한\s*수익|무조건|급등\s*확정|원금', '수익 약속'), (r'베팅|배팅|올인|몰빵|도박|대박|떡상|떡락|존버', '베팅 표현'),
          (r'(?<![A-Za-z])AI(?![A-Za-z])|인공지능|에이아이|GPT|챗봇|자동\s*(답글|댓글)', 'AI 언급'), (r'빚|대출\s*받아|신용\s*(거래|매수)', '빚'),
          (r'지금\s*당장|서두르|놓치면|마지막\s*기회', '긴급성'), (r'팔로우|맞팔|좋아요\s*(눌러|부탁)|리포스트\s*(해|부탁)|공유\s*부탁', '참여 구걸')]
T20_HOOK_BAN = SR_BAN[1:]
HOOKS = {
    '숫자대비': (lambda l: len(re.findall(r'\d+(?:[.,]\d+)?', l)) >= 2, '숫자 둘 이상'),
    '의외': (lambda l: bool(re.search(r'\d|그런데|인데|오히려|정작|없이', l)), '숫자 또는 뒤집는 말(인데·그런데·오히려·없이)'),
    '질문': (lambda l: bool(re.search(r'[?？]\s*$', l)), '첫 줄이 ?로 끝남'),
    '놓치는것': (lambda l: bool(re.search(r'놓치는|안 보는|모르는|지나치는|건너뛰는|빠뜨리는', l)), "'대부분이 놓치는/안 보는' 말"),
    '비교': (lambda l: bool(re.search(r'vs|VS|보다|대비|차이|같은 날|와 [^ ]+ 중|과 [^ ]+ 중', l)), 'vs·보다·대비·차이'),
    '경고': (lambda l: bool(re.search(r'주의|조심|함정|착시|오해|착각|위험|헷갈', l)), '주의·함정·착시·오해 같은 말'),
}
PEAKS_KST = ((7 * 60, 9 * 60), (12 * 60, 13 * 60), (18 * 60, 19 * 60), (20 * 60, 24 * 60))
HASHTAG = r'(?<![\w/&])#[^\s#]+'


def ad2_problems(name, txt, ig=False):
    out = []
    paras = re.split(r'\n\s*\n', txt.strip())
    for k, para in enumerate(paras):
        if '💊' not in para:
            continue
        lines = [l for l in para.split('\n') if l.strip()]
        body = [l for l in lines if not DIV.match(l)]
        has_div = (lines and DIV.match(lines[0])) or (k > 0 and all(DIV.match(l) for l in paras[k - 1].split('\n') if l.strip()))
        if not has_div:
            out.append(f'{name}: [AD2] 💊 문단 앞에 구분선 줄 없음')
        if k == 0 or (k == 1 and has_div and not (lines and DIV.match(lines[0]))):
            out.append(f'{name}: [AD2] 💊 문단이 맨 앞 — 그 회차 이야기 뒤에 둔다')
        if re.search(r'drkimworld\.com/r/|텔레그램|t\.me/|@drkimworld', '\n'.join(body)):
            out.append(f'{name}: [AD2] 💊 문단 안에 리포트·텔레그램 링크')
        if not re.search(WHO_S, para):
            out.append(f'{name}: [AD2] 💊 문단에 "누구"(조건·상황) 없음')
        if '광고' not in para:
            out.append(f"{name}: [AD2] 💊 문단에 '광고' 표시 없음")
        if not re.search(r'쿠팡 ?파트너스 활동의 일환', txt):
            out.append(f'{name}: [AD2] 쿠팡 파트너스 문장 없음')
        if 'health.drkimworld.com' in para:
            out.append(f'{name}: [AD2] 💊 문단에 건강몰 가이드 링크 — 쿠팡 제품 직접 링크로')
        if ig:
            if 'http' in para:
                out.append(f'{name}: [AD2] 인스타 캡션 💊 문단에 URL')
        elif not re.search(r'https://link\.coupang\.com/(a|re)/', para):
            out.append(f'{name}: [AD2] 💊 문단에 쿠팡 제품 직접 링크 없음')
    return out


def self_reply_problems(name, sr):
    out = []
    if not isinstance(sr, str) or not sr.strip():
        return [f'{name}: self_reply 가 비어 있음']
    if len(sr.strip()) > 150:
        out.append(f'{name}: self_reply {len(sr.strip())}자 > 150')
    for pat, why in SR_BAN:
        if re.search(pat, sr, re.I):
            out.append(f'{name}: self_reply 금지({why})')
    if not re.search(r'[?？]|주세요|남겨', sr):
        out.append(f'{name}: self_reply 는 그 회차 숫자를 묻는 짧은 질문')
    return out


def kst(publish_at):
    try:
        t = datetime.fromisoformat(str(publish_at or ''))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone(timedelta(hours=-5)))
    return t.astimezone(timezone(timedelta(hours=9)))


def t20_problems(name, d, kind, source_text=None):
    out = []
    t = d.get('text', '').strip()
    lines = [l for l in t.split('\n') if l.strip()]
    l1 = lines[0].strip() if lines else ''
    reps = [r.get('text', '') for r in d.get('replies', []) or []]
    if len(l1) > 40:
        out.append(f'{name}: [T20①] 첫 줄 훅 {len(l1)}자 > 40')
    hk = d.get('hook')
    if hk not in HOOKS:
        out.append(f'{name}: [T20①] "hook" 은 {"·".join(HOOKS)} 중 하나: {hk!r}')
    elif not HOOKS[hk][0](l1):
        out.append(f"{name}: [T20①] 훅 '{hk}'인데 첫 줄에 {HOOKS[hk][1]} 없음")
    for pat, why in T20_HOOK_BAN:
        if re.search(pat, l1, re.I):
            out.append(f'{name}: [T20①] 첫 줄 훅 금지({why})')
    if not lines or not re.search(r'[?？]', lines[-1]):
        out.append(f'{name}: [T20②] 본문 마지막 줄은 질문(?)으로 끝낸다')
    if re.search(r'https?://|www\.|drkimworld\.com|t\.me/', t) or d.get('link_attachment'):
        out.append(f'{name}: [T20③] 본문에 링크 — 리포트 링크는 답글(replies)로')
    tag = d.get('topic_tag')
    if not isinstance(tag, str) or not 1 <= len(tag.strip()) <= 50 or re.search(r'[.&#]', tag):
        out.append(f'{name}: [T20④] "topic_tag" 하나(1~50자, . & # 없이): {tag!r}')
    if re.search(HASHTAG, '\n'.join([t] + reps)):
        out.append(f'{name}: [T20④] Threads 본문·답글 해시태그 금지')
    if kind in ('th2', 'observe') and d.get('publish_at'):
        kt = kst(d.get('publish_at'))
        if kt and not any(a <= kt.hour * 60 + kt.minute < b for a, b in PEAKS_KST):
            out.append(f'{name}: [T20⑤] {kind} publish_at KST {kt:%H:%M} — 07–09·12–13·18–19·20–24시 안으로')
    if kind == 'observe':
        if d.get('channels') != ['threads']:
            out.append(f'{name}: [T20⑥] 관찰 글은 "channels": ["threads"]만')
        allx = '\n'.join([t] + reps + [str(d.get('self_reply') or '')])
        if re.search(r'https?://|www\.|\.com\b|t\.me/', allx):
            out.append(f'{name}: [T20⑥] 관찰 글에 링크 금지')
        if re.search(r'💊|광고|쿠팡|파트너스|리포트|영상|구독|텔레그램|@drkimworld|앱 설치|김박사', allx):
            out.append(f'{name}: [T20⑥] 관찰 글에 광고·홍보 금지')
        if reps:
            out.append(f'{name}: [T20⑥] 관찰 글은 이어지는 답글 없이 한 글')
        if d.get('poll'):
            out.append(f'{name}: [T20⑥] 관찰 글에 투표 금지')
        if source_text is None:
            out.append(f'{name}: [T20⑥] 관찰 글 출처 원문 없음')
        else:
            norm = source_text.replace(',', '')
            for n in re.findall(r'\d+(?:[.,]\d+)*', t):
                if n.replace(',', '') not in norm:
                    out.append(f'{name}: [T20⑥] 숫자 {n} 가 출처에 없음 — 지어낸 숫자 금지')
                    break
    else:
        rl = sum(len(re.findall(r'drkimworld\.com/r/', x)) for x in reps)
        if rl != 1:
            out.append(f'{name}: [T20③] 리포트 링크는 답글에 정확히 1개(지금 {rl}개)')
    if kind == 'th2':
        bl = [l.strip() for l in t.split('\n') if re.match(r'\s*·\s', l)]
        if len(bl) < 3:
            out.append(f"{name}: [T20⑦] 둘째 글은 '· ' 요약 줄 3개(지금 {len(bl)}개)")
        elif not any(re.search(r'\d{1,2}월 \d{1,2}일', l) for l in bl):
            out.append(f'{name}: [T20⑦] 둘째 글 요약 줄 하나는 다음 확인 날짜(○월 ○일)')
    return out


def s1_problems(name, d):
    out = []
    ch, t, m = d.get('channels', []), d.get('text', ''), d.get('media') or {}
    for c in [t] + [str((d.get('channel_text') or {}).get(x, '')) for x in ('instagram', 'facebook')]:
        for para in re.split(r'\n\s*\n', c):
            if '💊' not in para and 'health.drkimworld.com' not in para:
                continue
            if 'drkimworld.com/r/' in para or '텔레그램' in para or '@drkimworld' in para:
                out.append(f'{name}: [S1·수요공급] 💊 광고 줄이 리포트 링크·텔레그램 목록과 같은 문단')
            if not re.search(WHO_S, para):
                out.append(f'{name}: [S1·수요공급] 💊 문단에 "누구"(조건·상황 호명) 없음')
            if not re.search(r'광고|파트너스', para):
                out.append(f'{name}: [S1·수요공급] 💊 문단에 광고 표시 없음')
    if 'threads' in ch and t.strip():
        l1 = t.strip().split('\n')[0]
        if len(l1) > 45:
            out.append(f'{name}: [S1] Threads 첫 줄 {len(l1)}자 > 45')
        elif '\n\n' not in t.strip()[:len(l1) + 2]:
            out.append(f'{name}: [S1] Threads 첫 줄 뒤에 빈 줄')
        for para in re.split(r'\n\s*\n', t.strip()):
            if len(para) > 100:
                out.append(f'{name}: [S1] Threads 문단 {len(para)}자 > 100 — 문단을 나눈다: {para[:24]}…')
                break
    for c in ('instagram', 'facebook'):
        if c in ch and m.get('type') == 'reels':
            cap = (d.get('channel_text') or {}).get(c) or t
            l1 = cap.strip().split('\n')[0]
            if len(l1) > 45:
                out.append(f'{name}: [S1] {c} 릴스 캡션 첫 줄 {len(l1)}자 > 45')
            if c == 'instagram':
                if len(re.findall(HASHTAG, cap)) > 5:
                    out.append(f'{name}: [S1] 인스타 해시태그 5개 초과')
                if not str(m.get('cover', '')).endswith('cover_ig.jpg'):
                    out.append(f'{name}: [S1] 인스타 릴스 표지는 cover_ig.jpg')
                if m.get('trial'):
                    out.append(f'{name}: [S1] 체험 릴스(trial) 금지')
                if 'http' in cap:
                    out.append(f'{name}: 인스타 릴스 캡션에 URL 금지(프로필 링크 → 사이트 검색)')
                if not re.search(r'검색|프로필', cap):
                    out.append(f'{name}: 인스타 릴스 캡션에 프로필 링크·사이트 검색 안내가 있어야 함')
            if c == 'facebook' and len(re.findall(r'drkimworld\.com/r/', cap)) > 1:
                out.append(f'{name}: [S1] 페이스북 캡션 리포트 링크는 1개만')
    return out


def basic_problems(name, d):
    out = []
    o = d.get('poll') or []
    if o and not 2 <= len(o) <= 4:
        out.append(f'{name}: 투표 보기 2~4개: {len(o)}')
    for i, x in enumerate(o, 1):
        if len(str(x).encode()) > 25:
            out.append(f'{name}: poll[{i}] {len(str(x).encode())}바이트 > 25 (한글 1자 = 3바이트): {x}')
    if 'threads' in d.get('channels', []) and len(d.get('text', '')) > 500:
        out.append(f'{name}: Threads 본문 {len(d["text"])}자 > 500')
    for r in d.get('replies', []) or []:
        if len(r.get('text', '')) > 500:
            out.append(f'{name}: 답글 {len(r["text"])}자 > 500')
    allt = '\n'.join([d.get('text', '')] + [r.get('text', '') for r in d.get('replies', []) or []]
                     + [str(v) for v in (d.get('channel_text') or {}).values()])
    if '빚' in allt:
        out.append(f"{name}: '빚' 금지(빛 오인) → 부채·차입금")
    return out


def problems(name, d, kind, source_text=None):
    out = basic_problems(name, d) + s1_problems(name, d)
    ig_only = d.get('channels') == ['instagram']
    srcs = [('본문', d.get('text', ''), ig_only)] + [(f'답글{i + 1}', r.get('text', ''), False) for i, r in enumerate(d.get('replies', []) or [])]
    srcs += [(f'channel_text.{c}', v, c == 'instagram') for c, v in (d.get('channel_text') or {}).items()]
    for nm, txt, ig in srcs:
        out += ad2_problems(f'{name} {nm}', str(txt or ''), ig)
    if d.get('self_reply') is not None:
        if 'threads' not in d.get('channels', []):
            out.append(f'{name}: self_reply 는 Threads 글에만')
        else:
            out += self_reply_problems(name, d.get('self_reply'))
    if kind in ('th1', 'th2', 'observe'):
        out += t20_problems(name, d, kind, source_text)
    return out
