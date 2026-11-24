"""김박사 건강몰 방문·클릭 추적 스크립트(김박사 몰은 scripts/mall_build.py TRACK → /v1/mall 이 맡는다, 2026-11-20 운영자 "몰 페이지 트래픽좀 다각화해서 체계적으로 잘 추적해서 저장해놓고 인사이트로 활용해").

페이지를 떠날 때(숨겨질 때) 워커 /v1/mhit 로 한 번 보낸다(sendBeacon, text/plain → CORS 사전 요청 없음). 쿠키·개인 식별값 없음, sessionStorage 만.
- 유입 채널(세션 첫 페이지에서 정하고 세션 동안 유지): utm_source 우선, 없으면 리퍼러 호스트로
  search(구글·네이버·다음·빙…) · ai(챗GPT·퍼플렉시티·제미나이…) · youtube · social(Threads·인스타·페북·X) · messenger(카톡·텔레그램)
  · community(블로그·카페·커뮤니티) · email · internal(drkimworld.com·다른 몰) · referral · direct
- 세부 출처(sd): utm_source 또는 리퍼러 호스트, 캠페인(c): utm_campaign[.utm_medium]
- 클릭(k): 바깥으로 나가는 링크만 — coupang(쿠팡) · guide(건강몰 가이드) · youtube · site(본 사이트) · mall(다른 몰) · other.
  sub = 링크가 들어 있는 가장 가까운 [data-sub] 의 값(진열 '자리': deals·rank·c-food·g-omega3 …). 없으면 '-'
- 참여(en): 세션 누적 15초 이상 또는 스크롤 50% 이상이 처음 된 페이지에서 한 번
- 시청자 프로필(pf, 2026-11-24): 세션 첫 페이지의 aud= 값(health.yaml profiles 코드), 없으면 utm_campaign 의 영상 slug(-long/-short 뗌)를
  profile_map 으로 바꾼 값, 모르면 '-'. 세션 동안 유지. <html data-pf> 로 화면(프로필 상자)에 알려 준다.
  쿠팡 링크를 누르는 순간 하위 ID 뒤에 p<코드>를 붙인다(hmomega → hmomegapblood): 쿠팡 실적에서 프로필별 주문을 본다.
- 화면 안 행동(k=ui): window.hmEv('<이름>') — 프로필 상자·자가 점검·정렬 버튼(sub = 이름)
채널에서 몰로 보내는 링크는 utm 규칙을 따른다: ?utm_source=<채널>&utm_medium=<자리>&utm_campaign=<주제>
  (예: youtube·pinned·omega3-long / threads·post·omega3 / telegram·report·nvda / site·footer·mall)
"""
from __future__ import annotations

API = "https://api.drkimworld.com/v1/mhit"

_JS = r"""<script>(function(){try{var SITE='__SITE__',API='__API__',ss=window.sessionStorage,t0=Date.now(),vis=0,last=document.hidden?0:t0,sc=0,ks=[],sent=0;
var PATH=location.pathname.replace(/index\.html$/,'');var n=+(ss.getItem('mk_n')||0)+1;ss.setItem('mk_n',n);
function cls(h){h=(h||'').toLowerCase();if(!h)return 'direct';
if(/(^|\.)(google|naver|daum|bing|yahoo|yandex|duckduckgo|zum|ecosia|nate)\./.test(h)&&!/mail\./.test(h))return 'search';
if(/(chatgpt|openai|perplexity|gemini|copilot|claude|wrtn|you\.com)/.test(h))return 'ai';
if(/(youtube|youtu\.be)/.test(h))return 'youtube';
if(/(threads|instagram|facebook|fb\.|t\.co|twitter|x\.com|tiktok|linkedin)/.test(h))return 'social';
if(/(kakao|telegram|t\.me|line\.me|band\.us)/.test(h))return 'messenger';
if(/(blogger|blogspot|blog\.naver|tistory|cafe\.|dcinside|clien|fmkorea|ppomppu|reddit|theqoo|instiz)/.test(h))return 'community';
if(/mail/.test(h))return 'email';if(/drkimworld\.com$/.test(h))return 'internal';return 'referral';}
var S=null;try{S=JSON.parse(ss.getItem('mk_src')||'null')}catch(e){}
if(!S){var u=new URLSearchParams(location.search),us=(u.get('utm_source')||'').toLowerCase(),um=(u.get('utm_medium')||'').toLowerCase(),uc=(u.get('utm_campaign')||'').toLowerCase(),rh='';
try{rh=document.referrer?new URL(document.referrer).hostname.replace(/^(www|m)\./,''):''}catch(e){}
var ch;if(us){ch=/^(yt|youtube)$/.test(us)?'youtube':/^(threads|ig|instagram|fb|facebook|x|twitter|tiktok)$/.test(us)?'social':/^(telegram|tg|kakao|kakaotalk|band)$/.test(us)?'messenger':/^(blogger|blog|tistory|cafe|community)$/.test(us)?'community':/^(site|drkimworld|mall|health)$/.test(us)?'internal':/^(email|newsletter|mail)$/.test(us)?'email':/^(google|naver|daum|bing)$/.test(us)?'search':/^(chatgpt|perplexity|gemini|ai)$/.test(us)?'ai':cls(us+'.');if(ch==='direct')ch='referral';}
else ch=cls(rh);
var au=(u.get('aud')||'').toLowerCase(),PF=__PF__,PM=__PM__,pf=PF.indexOf(au)>=0?au:(PM[uc.replace(/-(long|short)$/,'')]||'-');
S={ch:ch,sd:(us||rh||ch).replace(/[^a-z0-9.-]/g,'').slice(0,40)||ch,c:(uc?uc+(um?'.'+um:''):'').slice(0,60),lp:PATH,pf:pf};ss.setItem('mk_src',JSON.stringify(S));}
var PFX=S.pf||'-';document.documentElement.setAttribute('data-pf',PFX);
window.hmEv=function(x){x=String(x||'').toLowerCase().replace(/[^a-z0-9_-]/g,'').slice(0,30);if(x&&ks.length<10)ks.push({k:'ui',sub:x})};
function secs(){return Math.round((vis+(last?Date.now()-last:0))/1000)}
addEventListener('scroll',function(){var d=document.documentElement,h=d.scrollHeight-innerHeight;if(h>0)sc=Math.max(sc,Math.min(100,Math.round(scrollY/h*100)))},{passive:true});
document.addEventListener('click',function(e){var a=e.target&&e.target.closest?e.target.closest('a[href]'):null;if(!a)return;var h;try{h=new URL(a.href,location.href)}catch(x){return}
if(h.host===location.host)return;var k=/coupang\.com$/.test(h.hostname)||/coupa\.ng$/.test(h.hostname)?'coupang':/^health\.drkimworld\.com$/.test(h.hostname)&&/^\/guide\//.test(h.pathname)?'guide':/(youtube\.com|youtu\.be)$/.test(h.hostname)?'youtube':/^(www\.)?drkimworld\.com$/.test(h.hostname)?'site':/^(mall|health)\.drkimworld\.com$/.test(h.hostname)?'mall':'other';
if(k==='coupang'&&PFX!=='-'){var si=h.searchParams.get('subid')||'';if(/^hm[a-z0-9]{1,20}$/.test(si)&&si.slice(-PFX.length-1)!=='p'+PFX){h.searchParams.set('subid',si+'p'+PFX);a.href=h.toString()}}
var b=a.closest('[data-sub]');if(ks.length<10)ks.push({k:k,sub:b?b.getAttribute('data-sub'):'-'});if(k!=='coupang')send();},true);
function send(){if(sent)return;sent=1;var a=secs(),cum=+(ss.getItem('mk_t')||0)+a;ss.setItem('mk_t',cum);var en=0;
if(!ss.getItem('mk_e')&&(cum>=15||sc>=50)){en=1;ss.setItem('mk_e','1')}
var b={site:SITE,p:PATH,lp:S.lp,ch:S.ch,sd:S.sd,c:S.c,pf:PFX,s:n,a:a,sc:sc,m:/Mobi|Android/i.test(navigator.userAgent)?1:0,en:en,k:ks};
try{navigator.sendBeacon(API,new Blob([JSON.stringify(b)],{type:'text/plain'}))}catch(x){}}
document.addEventListener('visibilitychange',function(){if(document.hidden){if(last){vis+=Date.now()-last;last=0}send()}else{last=Date.now();sent=0;ks=[];vis=0;n=+(ss.getItem('mk_n')||0)+1;ss.setItem('mk_n',n)}});
addEventListener('pagehide',function(){if(last){vis+=Date.now()-last;last=0}send()});}catch(e){}})();</script>"""


def snippet(site: str, profiles: list[str] | None = None, pmap: dict | None = None) -> str:
    """site = 'health'(건강몰). 워커는 health 만 받는다. profiles = 프로필 코드, pmap = 영상 slug → 코드(health.yaml)."""
    if site != "health":
        raise ValueError(site)
    import json
    codes = [c for c in (profiles or []) if c.isalpha() and c.islower() and 2 <= len(c) <= 8]
    pm = {k: v for k, v in (pmap or {}).items() if v in codes}
    return (_JS.replace("__SITE__", site).replace("__API__", API)
            .replace("__PF__", json.dumps(codes)).replace("__PM__", json.dumps(pm, separators=(",", ":"))))
