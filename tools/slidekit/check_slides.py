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
m=re.findall(r'\$[\d.,]+\s*(?:만|억)',open(d+'/slides.json',encoding='utf-8').read())
if m: print('MONEY','달러 기호와 만·억을 같이 씀(지침 A7):',m[:6]);ok=False
print('OK' if ok else 'FAIL')
