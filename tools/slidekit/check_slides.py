# slides.json 검증: 문장 번호(at/from)가 TTS 문장 수 안에 있는지, 다음 화면 전에 드러나는지, quote의 at==from인지, ad 문장이 사이트 안내인지 출력
# 영상 제작 지침 v1(2026-10-15): 첫 요소 at==from(A3, 실패 처리), '$+만/억' 표기 금지(A7), list 번호 배지 2자 이하
# 사용: python3 check_slides.py <video 폴더>  (slides.json, raw_timing.json이 있는 곳). 끝에 OK 또는 FAIL
import json,sys,re
d=sys.argv[1]
s=json.load(open(d+'/slides.json'));tm=json.load(open(d+'/raw_timing.json'))['paras']
assert len(s['paras'])==len(tm),(len(s['paras']),len(tm))
ok=True
for i,p in enumerate(s['paras']):
    n=len(tm[i]['sents']);sl=p['slides']
    for j,x in enumerate(sl):
        f=x.get('from',0);nxt=sl[j+1].get('from',0) if j+1<len(sl) else n
        ats=[f]+([x['at']] if 'at' in x else [])+[it['at'] for k in ('items','stats','points','lines','options') for it in x.get(k,[]) if isinstance(it,dict) and 'at' in it]+[x[k]['at'] for k in ('left','right') if k in x and 'at' in x[k]]+([x['foot_at']] if 'foot_at' in x else [])
        if f>=n or max(ats)>=min(n,nxt) or min(ats)<f: print('BAD p%d s%d'%(i+1,j),x.get('layout'),f,ats,'n',n,'next',nxt);ok=False
        if x.get('layout') in ('quote','source') and x.get('at',f)!=f: print('QUOTE p%d'%(i+1));ok=False
        els=ats[1:]
        if els and min(els)>f and x.get('layout')!='outro': print('BLANK p%d s%d'%(i+1,j),x.get('layout'),x.get('title',''),'첫 문장(%d) 동안 제목만 보임: 첫 요소의 at을 from과 같게(지침 A3)'%f);ok=False
        if x.get('layout')=='chart' and sum(1 for it in x.get('points',[]) if it.get('at',f)==f)<2: print('CHART1 p%d s%d'%(i+1,j),x.get('title',''),'첫 문장 동안 점이 하나뿐(빈 화면으로 잡힘): 첫 두 점의 at을 from과 같게');ok=False
        # CHART2: 차트 점을 나중 문장에 덧붙이면 화면 전환으로 잡히지 않아 긴 정지가 된다(AEHR p1·p5, IREN). 점은 모두 같은 at, 다음 내용은 새 슬라이드로
        if x.get('layout')=='chart' and len(set(it.get('at',f) for it in x.get('points',[])))>1: print('CHART2 p%d s%d'%(i+1,j),x.get('title',''),'점이 여러 문장에 나뉘어 나옴: 점은 한 번에, 다음 점은 새 슬라이드(compare·stat)로');ok=False
        for it in x.get('items',[]):
            if isinstance(it,dict) and len(str(it.get('no','')))>2: print('BADGE p%d'%(i+1),it.get('no'),'(번호 배지는 2자 이하)');ok=False
        # BIG: stat 큰 글자가 13자 이상이면 화면 밖으로 잘린다(10-17 TIA 13장). 긴 말은 title·label로
        for it in x.get('stats',[]):
            if isinstance(it,dict) and len(str(it.get('big','')))>12: print('BIG p%d s%d'%(i+1,j),it.get('big'),'(stat big은 12자 이하, 긴 말은 title·label로)');ok=False
    first=sl[0]; fa=[it.get('at',0) for k in ('items','stats','points','lines') for it in first.get(k,[]) if isinstance(it,dict)]+[first[k].get('at',0) for k in ('left','right') if k in first]
    if i==0 and fa and min(fa)>0: print('BAD p1 첫 화면이 첫 문장 동안 비어 있음 (훅 5초 이탈 위험): 첫 요소의 at을 0으로'); ok=False
    for a in p.get('ad',[]):
        if a>=n: print('ADBAD',i+1,a,n);ok=False
        else: print('ad p%d[%d]'%(i+1,a),tm[i]['sents'][a]['text'][:45])
# AD: 사이트 안내 문장('고정 댓글'·'홈페이지·무료')에는 "ad" 표시가 있어야 미드롤이 뜬다(2026-11-02 BTQ 49회차: "ad"를 빠뜨려 미드롤 0회·안내 문단 16초 정지로 합성 다시)
for i,(p,t) in enumerate(zip(s['paras'],tm)):
    for k,st in enumerate(t['sents']):
        if re.search(r'고정 댓글|홈페이지[^.]*무료|무료로 열려', st['text']) and k not in p.get('ad',[]) and k not in p.get('shop',[]): print('ADMISS p%d[%d] 사이트 안내 문장에 "ad" 표시 없음(미드롤 안 뜸):'%(i+1,k),st['text'][:40]);ok=False
if not any(p.get('ad') for p in s['paras']): print('ADMISS 미드롤 문단이 하나도 없음');ok=False
# ADTEXT: "ad" 표시 문장은 실제 안내 문장이어야 한다(운영자 지시 2026-11-11: AGNC 75회차에서 본문 문장 '직전 배수는 1.18배'에 ad가 붙어 음성 안내 없이 미드롤 전체 화면이 5초 뜸)
GUIDE=r'리포트|홈페이지|고정 댓글|설명란|무료|앱|팔로우|사이트'
for i,(p,t) in enumerate(zip(s['paras'],tm)):
    for a in p.get('ad',[]):
        if a<len(t['sents']) and not re.search(GUIDE,t['sents'][a]['text']): print('ADTEXT p%d[%d] ad 표시 문장에 안내(리포트·홈페이지·고정 댓글·설명란) 말이 없음 → 미드롤이 본문 위에 뜸:'%(i+1,a),t['sents'][a]['text'][:45]);ok=False
# ADMID: 영상 중반(35~75%)에 음성 안내 문장(ad)이 하나 이상(운영자 지시 2026-11-11: AGNC 안내가 21%·78%·93%뿐이라 중반 6분 공백)
dur=tm[-1]['sents'][-1]['end'] if tm[-1]['sents'] else 1
mid=[(i,a) for i,(p,t) in enumerate(zip(s['paras'],tm)) for a in p.get('ad',[]) if a<len(t['sents']) and 0.35<=t['sents'][a]['start']/dur<=0.75 and re.search(GUIDE,t['sents'][a]['text'])]
if not mid: print('ADMID 영상 35~75%% 구간(%d~%d초)에 사이트 안내 문장(ad)이 없음: 중반 반전 직전에 리포트 안내 한 문장을 넣는다'%(dur*0.35,dur*0.75));ok=False
# POLL: 롱폼 끝(마지막 두 문단 안)에 Threads 같은 투표 화면 1장(운영자 지시 2026-10-16). 보기 2~4개, 각 12자 이하
pl=[x for p in s['paras'][-2:] for x in p['slides'] if x.get('layout')=='poll']
if not pl: print('POLL 마지막 두 문단에 poll 화면이 없음: 끝에서 두 번째 문단에 투표(question·options·foot_at)를 넣는다');ok=False
for x in pl:
    o=x.get('options',[])
    if not 2<=len(o)<=4 or any(len(str(i.get('text','')))>12 for i in o): print('POLL 보기는 2~4개, 각 12자 이하:',[i.get('text') for i in o]);ok=False
# SHOP: 쿠팡 상품 카드(운영자 지시 2026-11-10). deck에 "shop"이 있으면 정확히 한 문장에 표시, 그 문장은 '설명란'이나 '고정 댓글'을 말하고 사이트 안내(ad)와 겹치지 않으며 12초 이하
if s.get('shop'):
    sh=[(i,k) for i,p in enumerate(s['paras']) for k in p.get('shop',[])]
    if len(sh)!=1: print('SHOP 쿠팡 카드 문장은 영상 전체에 정확히 1개:',sh);ok=False
    for i,k in sh:
        n=len(tm[i]['sents'])
        if k>=n: print('SHOP 문장 번호가 범위 밖 p%d[%d]'%(i+1,k));ok=False;continue
        st=tm[i]['sents'][k]
        if not re.search(r'설명란|고정 댓글',st['text']): print('SHOP p%d[%d] 카드 문장에 설명란·고정 댓글 안내가 없음:'%(i+1,k),st['text'][:40]);ok=False
        if k in s['paras'][i].get('ad',[]): print('SHOP p%d[%d] 사이트 안내(ad) 문장과 겹침'%(i+1,k));ok=False
        if st['end']-st['start']>12: print('SHOP p%d[%d] 카드 문장이 12초를 넘음(%.1f초)'%(i+1,k,st['end']-st['start']));ok=False
        if i>=len(s['paras'])-1: print('SHOP 마지막 문단(outro)에는 넣지 않음');ok=False
        else: print('shop p%d[%d]'%(i+1,k),st['text'][:45])
    st_txt=str(s.get('shop_strip') or '')
    if not st_txt: print('SHOP 쿠팡 짧은 띠 문구 "shop_strip"이 없음(2026-11-11 지침: 1/3·2/3·카드 직전 6초씩)');ok=False
    elif len(st_txt)>28 or '설명란' not in st_txt: print('SHOP shop_strip은 28자 이하, \'설명란\' 포함:',st_txt);ok=False
elif any(p.get('shop') for p in s['paras']): print('SHOP 문단에 shop 표시가 있는데 slides.json에 "shop" 이미지가 없음');ok=False
else: print('SHOPMISS 쿠팡 상품 카드(shop)가 없음: SKILL 쿠팡 장(yt-shop.yml → make_shop_card.py)으로 영상마다 한 장 넣는다(운영자 확인 2026-11-11, AGNC 75회차 누락)');ok=False
# SUB: 구독 요청 한 문장(운영자 지시 2026-11-17 "1 3만 수행" — 구독 전환 시험). 영상 전체에 정확히 1문장, '구독'이 들어가고,
# 첫 30초·outro·사이트 안내(ad)·쿠팡(shop) 문장이 아니다. 그 문장 동안 화면 아래 '구독' 띠가 뜬다(make_slide_video.py)
sb=[(i,k) for i,p in enumerate(s['paras']) for k in p.get('sub',[])]
if len(sb)!=1: print('SUBMISS 구독 요청 문장("sub": [문장 번호])은 영상 전체에 정확히 1개(SKILL V3 구독 요청):',sb);ok=False
for i,k in sb:
    if k>=len(tm[i]['sents']): print('SUB 문장 번호가 범위 밖 p%d[%d]'%(i+1,k));ok=False;continue
    st=tm[i]['sents'][k]
    if '구독' not in st['text']: print('SUB p%d[%d] 문장에 \'구독\'이 없음:'%(i+1,k),st['text'][:40]);ok=False
    if st['start']<30: print('SUB p%d[%d] 첫 30초(훅)에는 넣지 않음'%(i+1,k));ok=False
    if i>=len(s['paras'])-1: print('SUB 마지막 문단(outro)에는 넣지 않음(남은 시청자가 적다)');ok=False
    if k in s['paras'][i].get('ad',[]) or k in s['paras'][i].get('shop',[]): print('SUB p%d[%d] 사이트 안내·쿠팡 문장과 겹침(행동은 한 문장에 하나)'%(i+1,k));ok=False
    if re.search(r'놓치|보내 ?드|알려 ?드|업데이트',st['text']): print('SUB p%d[%d] 긴급성·업데이트 약속 표현 금지:'%(i+1,k),st['text'][:40]);ok=False
# NEXT: 이어 보기 띠(운영자 지시 2026-11-18 "종목 간 교차 링크 필수"). 문단 'next' = [안내 문장 번호], deck 'next_text'.
# 안내 문장은 '편'·'설명란'을 담고, 구독(sub)·사이트 안내(ad)·쿠팡(shop) 문장과 같은 문장이 아니다(NEXTSUB). 'next'를 쓰는 덱만 검사한다(옛 회차 오탐 없음)
nx=[(i,k) for i,p in enumerate(s['paras']) for k in p.get('next',[])]
if nx and not s.get('next_text'): print('NEXT "next_text"(띠 문구)가 없음');ok=False
for i,k in nx:
    if k>=len(tm[i]['sents']): print('NEXT 문장 번호가 범위 밖 p%d[%d]'%(i+1,k));ok=False;continue
    st=tm[i]['sents'][k]
    if k in s['paras'][i].get('sub',[]) or k in s['paras'][i].get('ad',[]) or k in s['paras'][i].get('shop',[]): print('NEXTSUB p%d[%d] 이어 보기 안내가 구독·사이트 안내·쿠팡 문장과 겹침'%(i+1,k));ok=False
    if not re.search(r'편',st['text']) or '설명란' not in st['text']: print('NEXT p%d[%d] 안내 문장에 \'편\'·\'설명란\'이 없음:'%(i+1,k),st['text'][:40]);ok=False
    else: print('next p%d[%d]'%(i+1,k),st['text'][:45])
    print('sub p%d[%d]'%(i+1,k),st['text'][:45])
# ANIM: 움직이는 장면(2026-11-16, SKILL V6.8 — 같은 날 운영자 "도움이 될 거 같은 장면이 있으면 전부"로 1~2컷 상한 없앰).
# 틀이 있는지, 박자 문장 번호가 그 슬라이드 안에서 커지는지, 안내(ad)·쿠팡 문장과 겹치지 않는지, 마지막 박자 뒤 정지가 12초를 넘지 않는지,
# 데이터 틀에 beats가 있는지(ANIMBEAT). 숫자·비교 장면(문단)인데 anim이 없으면 WARN ANIMCAND(실패 아님), 끝에 anim 문단 비율
import os
TPLS=[f[:-5] for f in os.listdir(os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates','anim')) if f.endswith('.html')] if os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates','anim')) else []
na=0
for i,(p,t) in enumerate(zip(s['paras'],tm)):
    n=len(t['sents']);sl=p['slides']
    for j,x in enumerate(sl):
        if not x.get('anim'): continue
        na+=1;an=x['anim'];dd=an.get('data',{});f=x.get('from',0);nxt=sl[j+1].get('from',0) if j+1<len(sl) else n
        if an.get('tpl') not in TPLS: print('ANIM p%d s%d 틀 없음:'%(i+1,j),an.get('tpl'),TPLS);ok=False
        bs=[b for k,v in dd.items() if k=='beats' or k.endswith('_beat') for b in (v if isinstance(v,list) else [v]) if b is not None]
        if any(not (f<=b<nxt) for b in bs): print('ANIM p%d s%d 박자 문장 번호가 슬라이드 범위(%d~%d) 밖:'%(i+1,j,f,nxt-1),bs);ok=False
        bl=[b for b in dd.get('beats',[]) if b is not None]
        if bl!=sorted(bl): print('ANIM p%d s%d beats는 커지는 순서로:'%(i+1,j),bl);ok=False
        rng=set(range(f,nxt))
        if rng&set(p.get('ad',[])) or rng&set(p.get('shop',[])): print('ANIMAD p%d s%d 움직이는 장면 구간에 안내(ad)·쿠팡 문장이 있음: 장면을 앞뒤로 옮긴다'%(i+1,j));ok=False
        if nxt<=n and bs:
            end=t['sents'][nxt-1]['end'] if nxt-1<n else t['end'];lb=t['sents'][max(bs)]['start']
            if end-lb>12: print('ANIMTAIL p%d s%d 마지막 박자 뒤 %.1f초 정지: 슬라이드를 나누거나 마지막 박자를 뒤 문장으로'%(i+1,j,end-lb));ok=False
        if dd.get('beats') is None and x['anim'].get('tpl')!='chalk_hook': print('ANIMBEAT p%d s%d %s에 beats(항목마다 문장 번호)가 없음: 내레이션 박자에 맞춘다'%(i+1,j,x['anim'].get('tpl')));ok=False
        print('anim p%d s%d'%(i+1,j),an.get('tpl'),'박자',bs)
# ANIMCAND(경고): 숫자·비교 장면 = chart·(양쪽 큰 글자가 숫자인) compare 슬라이드가 있거나 숫자 stat 슬라이드가 2장 이상인 문단(첫·끝 두 문단 제외). 그런데 anim이 하나도 없으면 알린다.
# 움직일 이유 없는 장면(제목·안내·쿠팡·미드롤·출처)은 정지 슬라이드 그대로. 목표는 롱폼 문단의 절반 안팎(SKILL V6.8)
anim_p=0;cand=[];np_=len(s['paras'])
for i,p in enumerate(s['paras']):
    has=any(x.get('anim') for x in p['slides']);anim_p+=has
    if has or i==0 or i>=np_-2: continue
    dig=lambda v: bool(re.search(r'\d',str(v)))
    num=[x for x in p['slides'] if x.get('layout')=='chart' or (x.get('layout')=='compare' and all(dig((x.get(k) or {}).get('big','')) for k in ('left','right'))) or (x.get('layout')=='stat' and any(dig(it.get('big','')) for it in x.get('stats',[]) if isinstance(it,dict)))]
    if any(x.get('layout') in ('chart','compare') for x in num) or len(num)>=2: cand.append(i)
for i in cand:
    x=next(x for x in s['paras'][i]['slides'] if x.get('layout') in ('chart','compare','stat') and re.search(r'\d',json.dumps(x,ensure_ascii=False)))
    print('WARN ANIMCAND p%d 숫자·비교 장면인데 anim 없음(%s \'%s\'): compare_bars·relative_lines·record_bars·scenario_bars·trend_line·live_chart 가운데 맞는 틀로'%(i+1,x.get('layout'),str(x.get('title',''))[:24]))
# ANIMRATIO 기준(운영자 2026-11-16 "롱폼 숏폼 모두 최대한 애니메이션"): ① 데이터 anim이 있는 문단이 본문 문단(끝 두 문단 투표·outro 제외)의 60% 이상(전: 기준 없음, '절반 안팎')
# ② 나머지 정지 슬라이드·미드롤·쿠팡·투표는 make_slide_video의 가벼운 움직임(motion)이 맡는다 — deck "motion": false면 실패
body=max(1,np_-2);anim_b=sum(1 for p in s['paras'][:np_-2] if any(x.get('anim') for x in p['slides']))
mo=s.get('motion',True) is not False
print('ANIMRATIO anim %d컷 · 문단 %d/%d (%.0f%%) · 본문 %d/%d (%.0f%%, 기준 60%%) · 가벼운 움직임 %s · 숫자 장면 중 정지 %d'%(na,anim_p,np_,100*anim_p/max(1,np_),anim_b,body,100*anim_b/body,'켬' if mo else '끔',len(cand)))
if anim_b<0.6*body: print('ANIMLOW 데이터 anim 문단 %d/%d < 60%%: 숫자·비교·흐름이 있는 문단마다 anim 틀(fromfig 6틀)을 넣는다(WARN ANIMCAND 목록부터)'%(anim_b,body));ok=False
if not mo: print('ANIMLOW slides.json "motion": false — 정지 슬라이드의 가벼운 움직임을 끄지 않는다(운영자 11-16 최대 적용)');ok=False
# BRAND(운영자 지시 2026-11-22 "인트로 영상을 만들어서 브랜드를 각인하고 아웃트로 영상도 넣어서 홍보장으로 활용", brand.py):
# 인트로 스팅 자리(첫 훅 문단 끝, 기본 = 시작이 15초 이상인 첫 문단 앞)와 엔드카드 홍보 칸. "outro_promo"는 2개 이하, 이름은 health·scorecard·alert·mall 또는
# {tag,title,sub,url,note}. 문구는 brand.problems(글자 수·금지 표현·URL은 도메인+경로)를 통과해야 한다. 'health'를 골랐는데 영양제 코드가 없으면 실패
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import brand
if s.get('brand_intro',True) is not False:
    bp=s.get('brand_intro_para') or next((i for i in range(1,len(tm)-1) if tm[i]['start']>=15.0),None)
    if not bp or not 0<bp<len(tm)-1: print('BRAND 인트로 자리 없음: brand_intro_para는 1 ~ 끝에서 두 번째 문단');ok=False
    else:
        print('brand intro p%d 앞 %.1f초(+2.4초 스팅)'%(bp+1,tm[bp]['start']))
        if tm[bp]['start']<15: print('WARN BRAND 인트로가 15초 전(%.1f초): 0초 훅·표지를 가리지 않게 첫 훅 문단 뒤로'%tm[bp]['start'])
        if tm[bp]['start']>90: print('WARN BRAND 인트로가 90초 뒤(%.1f초): 첫 훅 문단 끝에 둔다'%tm[bp]['start'])
if s.get('brand_end',True) is not False:
    op=s.get('outro_promo')
    if op is not None and (not isinstance(op,list) or len(op)>2 or any(not isinstance(x,dict) and x not in ('health',*brand.PROMOS) for x in op)): print('OUTRO_PROMO는 2개 이하 목록, 이름은 health·scorecard·alert·mall 또는 {tag,title,sub,url}:',op);ok=False
    elif op and 'health' in op and not brand.health_code(s): print('OUTRO_PROMO "health"를 골랐는데 영양제 중간광고 코드가 없음(deck "health": "H1|H2|H3" 또는 쿠팡 카드 h1_card.png)');ok=False
    else:
        ch=brand.pick(s)
        for k,c in ch:
            pr=brand.problems(c)
            if pr: print('OUTRO_PROMO',k,' / '.join(pr));ok=False
        print('brand end',[k for k,_ in ch] or '홍보 칸 없음')
        if brand.health_code(s) and any(k=='mall' for k,_ in ch): print('OUTRO_PROMO 영양제 광고 회차에 김박사 몰 칸(설명란 몰 줄과 같은 회차에 두지 않음, health_midroll 3절 5번)');ok=False
    if not any(x.get('layout')=='outro' for x in s['paras'][-1]['slides']): print('WARN BRAND 마지막 문단에 outro 슬라이드가 없어 엔드카드가 뜨지 않음')
m=re.findall(r'\$[\d.,]+\s*(?:만|억)',open(d+'/slides.json',encoding='utf-8').read())
if m: print('MONEY','달러 기호와 만·억을 같이 씀(지침 A7):',m[:6]);ok=False
print('OK' if ok else 'FAIL')
