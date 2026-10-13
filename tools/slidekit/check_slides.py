# slides.json 검증: 문장 번호(at/from)가 TTS 문장 수 안에 있는지, 다음 화면 전에 드러나는지, quote의 at==from인지, ad 문장이 사이트 안내인지 출력
# 사용: python3 check_slides.py <video 폴더>  (slides.json, raw_timing.json이 있는 곳). 끝에 OK 또는 FAIL
import json,sys
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
        if x.get('layout')=='quote' and x.get('at',f)!=f: print('QUOTE p%d'%(i+1));ok=False
    for a in p.get('ad',[]):
        if a>=n: print('ADBAD',i+1,a,n);ok=False
        else: print('ad p%d[%d]'%(i+1,a),tm[i]['sents'][a]['text'][:45])
print('OK' if ok else 'FAIL')
