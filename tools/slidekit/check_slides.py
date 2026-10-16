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
        ats=[f]+([x['at']] if 'at' in x else [])+[it['at'] for k in ('items','stats','points','lines') for it in x.get(k,[]) if isinstance(it,dict) and 'at' in it]+[x[k]['at'] for k in ('left','right') if k in x and 'at' in x[k]]
        if f>=n or max(ats)>=min(n,nxt) or min(ats)<f: print('BAD p%d s%d'%(i+1,j),x.get('layout'),f,ats,'n',n,'next',nxt);ok=False
        if x.get('layout') in ('quote','source') and x.get('at',f)!=f: print('QUOTE p%d'%(i+1));ok=False
        els=ats[1:]
        if els and min(els)>f and x.get('layout')!='outro': print('BLANK p%d s%d'%(i+1,j),x.get('layout'),x.get('title',''),'첫 문장(%d) 동안 제목만 보임: 첫 요소의 at을 from과 같게(지침 A3)'%f);ok=False
        if x.get('layout')=='chart' and sum(1 for it in x.get('points',[]) if it.get('at',f)==f)<2: print('CHART1 p%d s%d'%(i+1,j),x.get('title',''),'첫 문장 동안 점이 하나뿐(빈 화면으로 잡힘): 첫 두 점의 at을 from과 같게');ok=False
        # CHART2: 차트 점을 나중 문장에 덧붙이면 화면 전환으로 잡히지 않아 긴 정지가 된다(AEHR p1·p5, IREN). 점은 모두 같은 at, 다음 내용은 새 슬라이드로
        if x.get('layout')=='chart' and len(set(it.get('at',f) for it in x.get('points',[])))>1: print('CHART2 p%d s%d'%(i+1,j),x.get('title',''),'점이 여러 문장에 나뉘어 나옴: 점은 한 번에, 다음 점은 새 슬라이드(compare·stat)로');ok=False
        for it in x.get('items',[]):
            if isinstance(it,dict) and len(str(it.get('no','')))>2: print('BADGE p%d'%(i+1),it.get('no'),'(번호 배지는 2자 이하)');ok=False
    first=sl[0]; fa=[it.get('at',0) for k in ('items','stats','points','lines') for it in first.get(k,[]) if isinstance(it,dict)]+[first[k].get('at',0) for k in ('left','right') if k in first]
    if i==0 and fa and min(fa)>0: print('BAD p1 첫 화면이 첫 문장 동안 비어 있음 (훅 5초 이탈 위험): 첫 요소의 at을 0으로'); ok=False
    for a in p.get('ad',[]):
        if a>=n: print('ADBAD',i+1,a,n);ok=False
        else: print('ad p%d[%d]'%(i+1,a),tm[i]['sents'][a]['text'][:45])
m=re.findall(r'\$[\d.,]+\s*(?:만|억)',open(d+'/slides.json',encoding='utf-8').read())
if m: print('MONEY','달러 기호와 만·억을 같이 씀(지침 A7):',m[:6]);ok=False
print('OK' if ok else 'FAIL')
