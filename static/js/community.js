// 조회수·댓글·좋아요·많이 본 리포트·요즘 찾는 종목 (api.drkimworld.com)
// API가 꺼져 있거나 응답이 없으면 해당 영역을 숨긴 채로 둔다(사이트는 그대로 동작).
(function () {
  var KW = window.KW || {};
  var API = (KW.api || '').replace(/\/+$/, '');
  var base = KW.base || '';
  if (!API) return;

  // 기기 번호: 이 브라우저에만 저장하는 무작위 값. '내 댓글'·좋아요를 구분하는 데만 쓴다(같은 공용 IP를 쓰는 사람끼리 섞이지 않게)
  var DEV = (function () {
    var k = 'kw-did', v = '';
    try { v = localStorage.getItem(k) || ''; } catch (e) {}
    if (!/^[A-Za-z0-9_-]{22,64}$/.test(v)) {
      var b = new Uint8Array(18);
      (window.crypto || window.msCrypto).getRandomValues(b);
      v = btoa(String.fromCharCode.apply(null, b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      try { localStorage.setItem(k, v); } catch (e) {}
    }
    return v;
  })();
  function api(path, opt) {
    opt = opt || {};
    path += (path.indexOf('?') >= 0 ? '&' : '?') + 'd=' + DEV;
    var ctl = window.AbortController ? new AbortController() : null;
    var t = ctl ? setTimeout(function () { ctl.abort(); }, 6000) : 0;
    return fetch(API + path, {
      method: opt.method || 'GET',
      headers: opt.body ? { 'Content-Type': 'application/json' } : undefined,
      body: opt.body ? JSON.stringify(opt.body) : undefined,
      keepalive: !!opt.keepalive,
      credentials: 'include', // 로그인 쿠키(api.drkimworld.com, HttpOnly)
      signal: ctl ? ctl.signal : undefined
    }).then(function (r) {
      clearTimeout(t);
      return r.json().then(function (d) { d = d || {}; d._status = r.status; return d; });
    });
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function num(n) { return Number(n || 0).toLocaleString('ko-KR'); }
  // 프로필 동그라미: 사진이 있으면 사진, 없으면 닉네임 첫 글자(닉네임마다 색이 정해짐).
  // 사진 여부는 화면에 나온 사람들을 모아 한 번에 묻는다(/v1/avatars) — 사진 없는 사람마다 요청하지 않게
  var AV = {}, avWait = [], avTimer = 0;
  function paintAv(span, uid) {
    var v = AV[uid]; if (!v || span.getAttribute('data-av-v') === String(v)) return;
    var img = new Image(); img.alt = ''; img.decoding = 'async'; img.className = 'cm-av-img'; // 화면에 붙기 전에 읽으므로 lazy는 쓰지 않는다
    img.onload = function () { span.textContent = ''; span.appendChild(img); span.classList.add('has-img'); span.setAttribute('data-av-v', String(v)); };
    img.src = API + '/v1/avatar/' + uid + '?v=' + v;
  }
  function avLoad() {
    avTimer = 0;
    var need = {}; avWait.forEach(function (x) { if (!(x.uid in AV)) need[x.uid] = 1; });
    var ids = Object.keys(need).slice(0, 100), list = avWait; avWait = [];
    var done = function () { list.forEach(function (x) { paintAv(x.span, x.uid); }); };
    if (!ids.length) { done(); return; }
    api('/v1/avatars?ids=' + ids.join(',')).then(function (d) { ids.forEach(function (i) { AV[i] = (d.av || {})[i] || 0; }); done(); }).catch(function () {});
  }
  function seedAv(uid, v) { if (!uid) return; AV[uid] = v || 0; document.querySelectorAll('[data-av-uid="' + uid + '"]').forEach(function (sp) { if (v) paintAv(sp, uid); else { sp.classList.remove('has-img'); sp.removeAttribute('data-av-v'); sp.textContent = sp.getAttribute('data-av-l') || '?'; } }); }
  function avatar(nick, uid) {
    var n = String(nick || '?'), h = 0;
    for (var i = 0; i < n.length; i++) h = (h * 31 + n.charCodeAt(i)) >>> 0;
    var letter = n.replace(/^익명#/, '익').charAt(0);
    var a = el('span', 'cm-av', letter);
    a.style.background = 'hsl(' + (h % 360) + ' 42% 46%)';
    a.setAttribute('aria-hidden', 'true'); a.setAttribute('data-av-l', letter);
    if (uid) {
      a.setAttribute('data-av-uid', uid);
      if (uid in AV) paintAv(a, uid); else { avWait.push({ span: a, uid: uid }); if (!avTimer) avTimer = setTimeout(avLoad, 60); }
    }
    return a;
  }
  // 선 하트 아이콘(누르면 채워짐)
  function heart() {
    var ns = 'http://www.w3.org/2000/svg', v = document.createElementNS(ns, 'svg');
    v.setAttribute('class', 'ic'); v.setAttribute('viewBox', '0 0 24 24'); v.setAttribute('width', '17'); v.setAttribute('height', '17'); v.setAttribute('aria-hidden', 'true');
    var p = document.createElementNS(ns, 'path'); p.setAttribute('d', 'M12 20.5s-7.5-4.6-9.3-9.2C1.4 7.9 3.6 4.5 7 4.5c2 0 3.6 1.1 5 3 1.4-1.9 3-3 5-3 3.4 0 5.6 3.4 4.3 6.8-1.8 4.6-9.3 9.2-9.3 9.2z');
    v.appendChild(p); return v;
  }
  function setHeart(b, n, on) { b.textContent = ''; b.appendChild(heart()); b.appendChild(el('span', null, n ? num(n) : '')); b.setAttribute('aria-pressed', on ? 'true' : 'false'); b.setAttribute('aria-label', '좋아요 ' + (n || 0)); }
  function ago(ms) {
    var s = Math.max(0, (Date.now() - ms) / 1000);
    if (s < 60) return '방금';
    if (s < 3600) return Math.floor(s / 60) + '분 전';
    if (s < 86400) return Math.floor(s / 3600) + '시간 전';
    if (s < 86400 * 30) return Math.floor(s / 86400) + '일 전';
    var d = new Date(ms); return d.getFullYear() + '.' + (d.getMonth() + 1) + '.' + d.getDate();
  }

  // $TSLA 같은 종목 표시를 그 종목 페이지 링크로(사이트에 있는 종목만). 나머지는 글자 그대로(HTML로 해석하지 않음)
  var TK = {}; (KW.tk || []).forEach(function (t) { TK[t.c] = t.n; });
  function richText(node, text) {
    // $티커(사이트에 있는 종목) → 종목 페이지, @닉네임 → 그 사람 프로필
    var re = /\$([A-Za-z]{1,6})(?![A-Za-z])|@([가-힣A-Za-z0-9_]{2,12})/g, last = 0, m;
    text = String(text || '');
    while ((m = re.exec(text))) {
      var a;
      if (m[1]) {
        var code = m[1].toUpperCase();
        if (!TK[code]) continue;
        a = el('a', 'cashtag', '$' + code); a.href = base + '/t/' + code.toLowerCase() + '/'; a.title = TK[code];
      } else { a = el('a', 'mention', '@' + m[2]); a.href = base + '/u/?n=' + encodeURIComponent(m[2]); }
      if (m.index > last) node.appendChild(document.createTextNode(text.slice(last, m.index)));
      node.appendChild(a); last = m.index + m[0].length;
    }
    if (last < text.length) node.appendChild(document.createTextNode(text.slice(last)));
    return node;
  }

  // ---------- 리포트: 조회수 ----------
  var art = document.querySelector('article.report[data-slug]');
  var slug = art && art.getAttribute('data-slug');
  if (slug) {
    api('/v1/view', { method: 'POST', body: { slug: slug }, keepalive: true }).then(function (d) {
      var v = document.querySelector('[data-views]');
      if (v && d.views) { v.textContent = '조회 ' + num(d.views); v.hidden = false; }
    }).catch(function () {});
  }

  // ---------- 게시물 반응(피드 카드·리포트 공통): 좋아요·댓글 수·조회수·대표 댓글 ----------
  function postSlug(n) { var c = n.closest('[data-slug]'); return c && c.getAttribute('data-slug'); }
  function setLike(sl, likes, on) {
    document.querySelectorAll('[data-post-like]').forEach(function (b) {
      if (postSlug(b) !== sl) return;
      b.hidden = false; b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.querySelector('[data-n]').textContent = likes ? num(likes) : '';
    });
  }
  var postEls = Array.prototype.slice.call(document.querySelectorAll('[data-post-like]'));
  var slugs = postEls.map(postSlug).filter(function (x, i, a) { return x && a.indexOf(x) === i; });
  if (slugs.length) {
    api('/v1/stats?slugs=' + slugs.slice(0, 60).join(',')).then(function (d) {
      var st = d.stats || {};
      Object.keys(st).forEach(function (sl) {
        var x = st[sl];
        setLike(sl, x.likes, x.liked);
        paintRepost('r', sl, x.reposts, x.reposted);
        document.querySelectorAll('[data-post-cm]').forEach(function (n) { if (postSlug(n) === sl) n.textContent = x.comments ? num(x.comments) : ''; });
        document.querySelectorAll('[data-post-views]').forEach(function (n) {
          if (postSlug(n) !== sl || !x.views) return;
          n.textContent = num(x.views); n.parentNode.hidden = false;
        });
        document.querySelectorAll('[data-post-top]').forEach(function (n) {
          if (postSlug(n) !== sl || !x.top) return;
          n.textContent = '';
          n.appendChild(avatar(x.top.nick));
          var t = el('span', 'post-top-txt');
          t.appendChild(el('strong', null, x.top.nick + ' '));
          t.appendChild(document.createTextNode(x.top.body));
          n.appendChild(t);
          if (x.top.likes) n.appendChild(el('span', 'post-top-n muted', '♥ ' + num(x.top.likes)));
          n.hidden = false;
        });
      });
    }).catch(function () {});
  }
  // 행동 이벤트: 로그인 시작·좋아요
  document.addEventListener('click', function (e) {
    if (!window.kwEv || !e.target.closest) return;
    if (e.target.closest('.kw-login')) kwEv('login_start');
    if (e.target.closest('[data-post-like], .pa-like, .cm-like')) kwEv('like');
  }, true);
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-post-like]'); if (!b) return;
    var sl = postSlug(b); if (!sl || b.disabled) return;
    var on = b.getAttribute('aria-pressed') !== 'true';
    b.classList.remove('pop'); void b.offsetWidth; if (on) b.classList.add('pop');
    b.disabled = true;
    api('/v1/like', { method: 'POST', body: { slug: sl } }).then(function (d) {
      b.disabled = false;
      if (d._status === 200) setLike(sl, d.likes, d.liked);
    }).catch(function () { b.disabled = false; });
  });

  // ---------- 공통: 글 묶음(slug) → 주소 ----------
  // 커뮤니티 하나: 글은 종목 태그(b-티커)나 태그 없음(b-talk)으로만 나뉜다
  function threadUrl(sl) {
    var m = /^b-(.+)$/.exec(sl || '');
    return m && m[1] !== 'talk' ? base + '/t/' + m[1] + '/#community' : base + '/';
  }
  function threadLabel(sl) { var m = /^b-(.+)$/.exec(sl || ''); return m && m[1] !== 'talk' ? m[1].toUpperCase() + ' 커뮤니티' : '커뮤니티'; }
  function postUrl(id) { return base + '/p/?id=' + id; }
  // 글 하나로 가는 주소: 종토방·라운지 글은 글 상세, 리포트 댓글은 그 리포트 댓글 칸
  function itemUrl(sl, id) { return /^b-/.test(sl || '') && id ? postUrl(id) : threadUrl(sl); }
  function profileUrl(uid) { return base + '/u/?id=' + uid; }
  function nickEl(c, cls) {
    if (!c.uid) return el('strong', cls, c.nick);
    var a = el('a', cls + ' cm-nick-link', c.nick); a.href = profileUrl(c.uid); return a;
  }

  // ---------- 계정(계정 키): 이메일·전화 없이 닉네임만. 키는 이 브라우저에만 저장 ----------
  var ME = null, UNREAD = 0, LOGGED = false, PROVIDERS = [], DMN = 0, DMREQ = 0, BLOCKED = {};
  // ?naver=test 로 열면 검수 전 네이버 로그인 버튼을 보인다(운영자 시험·검수 캡처용). 한 번 열면 이 브라우저 세션 동안 유지
  var NT = /[?&]naver=test/.test(location.search); try { if (NT) sessionStorage.setItem('kw_nt', '1'); else NT = sessionStorage.getItem('kw_nt') === '1'; } catch (e) {}
  var meReady = api('/v1/me' + (NT ? '?nt=1' : '')).then(function (d) {
    ME = d.user || null; UNREAD = d.unread || 0; LOGGED = !!d.loggedIn; PROVIDERS = d.providers || [];
    DMN = d.dmUnread || 0; DMREQ = d.dmRequests || 0; BLOCKED = {}; (d.blocked || []).forEach(function (x) { BLOCKED[x] = 1; });
    if (ME) seedAv(ME.id, ME.av);
    paintHeader(); hideBlocked(); return ME;
  }).catch(function () { return null; });
  // 머리줄 버튼이 많아 한 줄을 넘으면(로그인·앱 설치·탭 줄 없는 화면) 이름표를 숨기고, 그래도 넘으면 사이트 이름 글자를 숨긴다
  function fitHeader() {
    var row = document.querySelector('.header-row'); if (!row) return;
    var over = function () { return row.scrollWidth > row.clientWidth + 1; };
    row.classList.remove('hdr-compact', 'hdr-tight');
    if (over()) row.classList.add('hdr-compact');
    if (over()) row.classList.add('hdr-tight');
  }
  addEventListener('resize', fitHeader);
  window.kwFitHeader = fitHeader;
  function isBlocked(uid) { return !!(uid && BLOCKED[uid]); }
  function hideBlocked() { // 차단한 사람의 글은 내 화면에서 숨긴다
    document.querySelectorAll('[data-by-uid]').forEach(function (n) { if (isBlocked(+n.getAttribute('data-by-uid'))) n.hidden = true; });
  }
  function paintHeader() {
    var lab = document.querySelector('[data-account-label]'); if (lab) lab.textContent = ME ? '내 계정' : '로그인';
    var bell = document.querySelector('[data-open-bell]'); if (bell) bell.hidden = !ME;
    document.querySelectorAll('[data-bell-n]').forEach(function (n) { n.hidden = !UNREAD; n.textContent = UNREAD > 9 ? '9+' : String(UNREAD); });
    var me = document.querySelector('[data-tab-me] span'); if (me) me.textContent = ME ? '내 정보' : '로그인';
    var dm = document.querySelector('[data-open-dm]'); if (dm) dm.hidden = !ME;
    fitHeader();
    document.querySelectorAll('[data-dm-n]').forEach(function (n) { var k = DMN + DMREQ; n.hidden = !k; n.textContent = k > 9 ? '9+' : String(k); });
  }
  var dlg = null;
  function dialog(title) {
    if (!dlg) {
      dlg = el('dialog', 'kw-dlg');
      document.body.appendChild(dlg);
      dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
    }
    dlg.textContent = '';
    var head = el('div', 'kw-dlg-head'); head.appendChild(el('h2', null, title));
    var x = el('button', 'kw-dlg-x', '×'); x.type = 'button'; x.setAttribute('aria-label', '닫기'); x.addEventListener('click', function () { dlg.close(); });
    head.appendChild(x); dlg.appendChild(head);
    var body = el('div', 'kw-dlg-body'); dlg.appendChild(body);
    if (!dlg.open) { if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', ''); }
    return body;
  }
  function field(label, input) { var w = el('label', 'kw-field'); w.appendChild(el('span', null, label)); w.appendChild(input); return w; }
  function btn(text, cls, fn) { var b = el('button', cls || 'btn', text); b.type = 'button'; if (fn) b.addEventListener('click', fn); return b; }
  var PNAME = { google: 'Google로 로그인', kakao: '카카오 로그인', naver: '네이버 로그인' };
  function loginUrl(prov) { return API + '/v1/auth/' + prov + '/start?return=' + encodeURIComponent(location.pathname + location.search.replace(/[?&]login=\w+/, '') + location.hash); }

  function openAccount() {
    meReady.then(function () {
      var msg = el('p', 'kw-msg'); msg.setAttribute('role', 'status');
      if (!LOGGED) { // 로그인 전: 구글·카카오 버튼
        var body = dialog('로그인');
        body.appendChild(el('p', 'muted', '로그인하면 닉네임이 고정되고, 팔로우·답글 알림을 쓸 수 있습니다(글은 로그인 없이도 쓸 수 있어요). 로그인할 때 이메일·이름·전화번호는 받지 않고, 같은 사람인지 알아보는 회원 번호만 씁니다.'));
        if (!PROVIDERS.length) body.appendChild(el('p', 'kw-warn', '로그인을 준비하고 있습니다. 잠시 뒤 다시 와 주세요.'));
        PROVIDERS.forEach(function (pv) { var a = el('a', 'btn kw-login kw-login-' + pv, PNAME[pv] || pv); a.href = loginUrl(pv); body.appendChild(a); });
        if (window.kwCanInstall && kwCanInstall()) body.appendChild(btn('📱 홈 화면에 앱으로 설치', 'btn kw-login', function () { dlg.close(); kwInstall(); }));
        var tl = el('p', 'muted kw-small'); tl.appendChild(document.createTextNode('로그인하면 ')); var ta = el('a', null, '이용약관'); ta.href = base + '/terms/'; ta.target = '_blank'; tl.appendChild(ta); tl.appendChild(document.createTextNode('에 동의한 것으로 봅니다.')); body.appendChild(tl);
        return;
      }
      if (!ME) { // 로그인은 했지만 계정이 아직 없음: 묻지 않고 닉네임을 자동으로 지어 바로 가입(나중에 언제든 변경)
        var body2 = dialog('가입하는 중…');
        body2.appendChild(msg);
        api('/v1/me', { method: 'POST', body: { auto: true } }).then(function (d) {
          if (!d.ok) { msg.textContent = d.message || '가입하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; return; }
          if (window.kwEv) kwEv('signup');
          var nn = (d.user && d.user.nick) || '';
          var h = dlg.querySelector('.kw-dlg-head h2'); if (h) h.textContent = '가입 완료';
          body2.textContent = '';
          var p1 = el('p'); p1.appendChild(document.createTextNode('닉네임은 ')); p1.appendChild(el('strong', null, nn)); p1.appendChild(document.createTextNode('(으)로 정해 두었어요.'));
          body2.appendChild(p1);
          body2.appendChild(el('p', 'muted', '마음에 안 들면 "내 계정"에서 언제든 바꿀 수 있어요.'));
          var row = el('div', 'kw-row');
          row.appendChild(btn('시작하기', 'btn btn-primary', function () { location.reload(); }));
          row.appendChild(btn('지금 바꾸기', 'btn', function () { try { sessionStorage.setItem('kw_open_acct', '1'); } catch (e) {} location.reload(); }));
          body2.appendChild(row);
          dlg.addEventListener('close', function () { location.reload(); }, { once: true });
        }).catch(function () { msg.textContent = '가입하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; });
        body2.appendChild(btn('로그아웃', 'cm-link', logout));
        return;
      }
      var body3 = dialog('내 계정');
      var info = el('div', 'kw-me'); info.appendChild(avatar(ME.nick, ME.id));
      var nm = el('div', 'kw-me-who'); var nmTop = el('div'); nmTop.appendChild(el('strong', null, ME.nick)); nmTop.appendChild(el('span', 'muted', ' · ' + new Date(ME.created).toLocaleDateString('ko-KR') + ' 가입')); nm.appendChild(nmTop);
      info.appendChild(nm); body3.appendChild(info);
      // 프로필 사진: 동그라미 안 수정 버튼을 누르면 바로 고르고 올린다
      editableAv(info.querySelector('.cm-av'), function (t) { msg.textContent = t; }, function () { phDel.hidden = !ME.av; });
      var phDel = btn('사진 지우기', 'cm-link kw-photo-del', function () {
        if (!confirm('프로필 사진을 지울까요?')) return;
        api('/v1/me/avatar/delete', { method: 'POST' }).then(function () { ME.av = 0; seedAv(ME.id, 0); phDel.hidden = true; msg.textContent = '사진을 지웠습니다.'; });
      });
      phDel.hidden = !ME.av; nm.appendChild(phDel);
      body3.appendChild(el('p', 'muted kw-small', '사진 속 연필을 누르면 바꿀 수 있어요. 사진은 모든 사람에게 보이며, 다른 사람의 얼굴·음란하거나 불쾌한 사진은 신고되면 내려갑니다.'));
      // 닉네임 바꾸기: 14일에 한 번
      var nk = el('input'); nk.maxLength = 12; nk.value = ME.nick; nk.autocomplete = 'off';
      var canNick = !ME.nickNext || Date.now() >= ME.nickNext;
      var nkRow = el('div', 'kw-row');
      var nkHint = el('p', 'muted kw-small', canNick ? '닉네임은 14일에 한 번 바꿀 수 있습니다. 바꾸면 지난 글의 이름도 함께 바뀝니다.'
        : new Date(ME.nickNext).toLocaleDateString('ko-KR') + '부터 다시 바꿀 수 있습니다(14일에 한 번).');
      nk.disabled = !canNick;
      body3.appendChild(field('닉네임', nk));
      if (canNick) nkRow.appendChild(btn('닉네임 변경', 'btn', function () {
        var v = nk.value.trim();
        if (v === ME.nick) { msg.textContent = '지금과 같은 닉네임입니다.'; return; }
        if (!confirm('닉네임을 "' + v + '"(으)로 바꿀까요? 바꾼 뒤 14일 동안은 다시 바꿀 수 없습니다.')) return;
        api('/v1/me', { method: 'POST', body: { nick: v, bio: ME.bio || '' } }).then(function (d) {
          if (!d.ok) { msg.textContent = d.message || '바꾸지 못했습니다.'; return; }
          location.reload();
        }).catch(function () { msg.textContent = '바꾸지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; });
      }));
      body3.appendChild(nkRow); body3.appendChild(nkHint);
      var bio2 = el('input'); bio2.maxLength = 80; bio2.value = ME.bio || ''; bio2.placeholder = '한 줄 소개';
      body3.appendChild(field('소개', bio2));
      var row = el('div', 'kw-row');
      row.appendChild(btn('소개 저장', 'btn', function () {
        api('/v1/me', { method: 'POST', body: { bio: bio2.value } }).then(function (d) { msg.textContent = d.ok ? '저장했습니다.' : (d.message || '저장하지 못했습니다.'); if (d.ok) ME.bio = bio2.value; });
      }));
      var pf = el('a', 'btn', '내 프로필'); pf.href = profileUrl(ME.id); row.appendChild(pf);
      var dmA = el('a', 'btn', '쪽지함'); dmA.href = base + '/dm/'; row.appendChild(dmA);
      row.appendChild(btn('알림', 'btn', openBell));
      if (window.kwCanInstall && kwCanInstall()) row.appendChild(btn('앱으로 설치', 'btn', function () { dlg.close(); kwInstall(); }));
      body3.appendChild(row);
      // 쪽지 받기 설정 + 차단 목록
      var pref = el('select');
      [['all', '누구나 (처음 보는 사람은 요청함으로)'], ['following', '내가 팔로우한 사람만'], ['none', '받지 않음 (내가 팔로우한 사람은 예외)']].forEach(function (o) {
        var op = el('option', null, o[1]); op.value = o[0]; if ((ME.dmPref || 'all') === o[0]) op.selected = true; pref.appendChild(op);
      });
      pref.addEventListener('change', function () {
        api('/v1/me', { method: 'POST', body: { dmPref: pref.value } }).then(function (d) { msg.textContent = d.ok ? '쪽지 받기 설정을 바꿨습니다.' : (d.message || '바꾸지 못했습니다.'); if (d.ok) ME.dmPref = pref.value; });
      });
      body3.appendChild(field('쪽지 받기', pref));
      body3.appendChild(btn('차단한 사용자 관리', 'cm-link', openBlocks));
      body3.appendChild(msg);
      api('/v1/admin/whoami').then(function (w) { if (!w.owner) return; var st = el('a', 'btn', '운영 통계'); st.href = base + '/admin/'; row.appendChild(st); }).catch(function () {});
      body3.appendChild(el('hr'));
      body3.appendChild(btn('로그아웃', 'btn', logout));
      body3.appendChild(btn('계정 삭제', 'cm-link kw-danger', function () {
        var all = confirm('계정을 삭제합니다. 내가 쓴 글도 모두 지울까요?\n[확인] 글도 모두 삭제\n[취소] 글은 "탈퇴한 사용자"로 남김');
        if (!confirm('정말 계정을 삭제할까요? 되돌릴 수 없습니다.')) return;
        api('/v1/me/delete', { method: 'POST', body: { all: all } }).then(function () { location.reload(); });
      }));
    });
  }
  // 내 사진 동그라미에 연필(수정) 버튼을 얹는다. 누르면 사진 고르기 → 줄이기 → 올리기
  function editableAv(av, say, after) {
    if (!av || !ME) return;
    var wrap = el('span', 'av-edit-wrap'); av.parentNode.insertBefore(wrap, av); wrap.appendChild(av);
    var file = el('input'); file.type = 'file'; file.accept = 'image/*'; file.hidden = true; wrap.appendChild(file);
    var b = el('button', 'av-edit'); b.type = 'button'; b.setAttribute('aria-label', ME.av ? '프로필 사진 바꾸기' : '프로필 사진 올리기'); b.title = b.getAttribute('aria-label');
    b.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    b.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); file.click(); });
    wrap.appendChild(b);
    file.addEventListener('change', function () {
      var f = file.files && file.files[0]; if (!f) return;
      file.value = '';
      cropImage(f, 256).then(function (blob) {
        wrap.classList.add('busy'); say('사진을 올리는 중…');
        return fetch(API + '/v1/me/avatar?d=' + DEV, { method: 'POST', body: blob, headers: { 'Content-Type': blob.type }, credentials: 'include' }).then(function (r) { return r.json(); });
      }).then(function (d) {
        wrap.classList.remove('busy');
        if (!d.ok) { say(d.message || '사진을 올리지 못했습니다.'); return; }
        ME.av = d.av; seedAv(ME.id, d.av); say('프로필 사진을 바꿨습니다.'); b.setAttribute('aria-label', '프로필 사진 바꾸기');
        if (window.kwEv) kwEv('avatar_set');
        if (after) after();
      }).catch(function (e) { wrap.classList.remove('busy'); if (e !== 'cancel') say('이 사진은 쓸 수 없습니다. 다른 사진(JPG·PNG)으로 해 보세요.'); });
    });
  }
  // 캔버스를 webp(안 되면 jpeg)로. 60KB를 넘으면 화질을 낮춘다
  function encodeCanvas(c) {
    return new Promise(function (ok, no) {
      var q = 0.86, type = 'image/webp';
      (function enc() {
        c.toBlob(function (b) {
          if (!b) { no(); return; }
          if (type === 'image/webp' && b.type !== 'image/webp') { type = 'image/jpeg'; enc(); return; }
          if (b.size > 60000 && q > 0.4) { q -= 0.15; enc(); return; }
          ok(b);
        }, type, q);
      })();
    });
  }
  // 사진 위치·크기 맞추기: 끌어서 옮기고, 막대·두 손가락·마우스 휠로 확대/축소. 동그라미 안이 프로필이 된다
  function cropImage(f, size) {
    return new Promise(function (ok, no) {
      if (!/^image\//.test(f.type || 'image/')) { no(); return; }
      var url = URL.createObjectURL(f), img = new Image();
      img.onerror = function () { URL.revokeObjectURL(url); no(); };
      img.onload = function () {
        var W = img.naturalWidth, H = img.naturalHeight; if (!W || !H) { no(); return; }
        var V = Math.min(280, window.innerWidth - 80);
        var d = el('dialog', 'kw-dlg crop-dlg'); document.body.appendChild(d);
        var head = el('div', 'kw-dlg-head'); head.appendChild(el('h2', null, '사진 위치 맞추기'));
        var x0 = el('button', 'kw-dlg-x', '×'); x0.type = 'button'; x0.setAttribute('aria-label', '닫기'); head.appendChild(x0); d.appendChild(head);
        var body = el('div', 'kw-dlg-body crop-body'); d.appendChild(body);
        var stage = el('div', 'crop-stage'); stage.style.width = stage.style.height = V + 'px';
        var pic = img; pic.className = 'crop-img'; pic.draggable = false; pic.alt = '';
        stage.appendChild(pic); stage.appendChild(el('div', 'crop-ring'));
        body.appendChild(stage);
        var row = el('div', 'crop-zoom');
        var minus = btn('−', 'crop-zb', null), plus = btn('+', 'crop-zb', null);
        minus.setAttribute('aria-label', '축소'); plus.setAttribute('aria-label', '확대');
        var range = el('input'); range.type = 'range'; range.min = '1'; range.max = '4'; range.step = '0.01'; range.value = '1'; range.setAttribute('aria-label', '확대/축소');
        row.appendChild(minus); row.appendChild(range); row.appendChild(plus); body.appendChild(row);
        body.appendChild(el('p', 'muted kw-small crop-hint', '사진을 끌어서 옮기고, 막대나 두 손가락으로 크기를 맞추세요. 동그라미 안이 프로필 사진이 됩니다.'));
        var acts = el('div', 'kw-row crop-acts'); body.appendChild(acts);
        var s0 = V / Math.min(W, H), z = 1, sc = s0, x = (V - W * sc) / 2, y = (V - H * sc) / 2;
        function clamp() {
          x = Math.min(0, Math.max(V - W * sc, x)); y = Math.min(0, Math.max(V - H * sc, y));
        }
        function draw() { clamp(); pic.style.width = W * sc + 'px'; pic.style.height = H * sc + 'px'; pic.style.transform = 'translate(' + x + 'px,' + y + 'px)'; range.value = String(z); }
        function zoomTo(nz, fx, fy) { // (fx, fy) 점이 그 자리에 머물도록
          nz = Math.max(1, Math.min(4, nz)); if (fx == null) { fx = V / 2; fy = V / 2; }
          var ns = s0 * nz; x = fx - (fx - x) * (ns / sc); y = fy - (fy - y) * (ns / sc); z = nz; sc = ns; draw();
        }
        range.addEventListener('input', function () { zoomTo(+range.value); });
        minus.addEventListener('click', function () { zoomTo(z / 1.2); }); plus.addEventListener('click', function () { zoomTo(z * 1.2); });
        stage.addEventListener('wheel', function (e) { e.preventDefault(); var r = stage.getBoundingClientRect(); zoomTo(z * Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top); }, { passive: false });
        var pts = {}, last = null, pinch = null;
        function local(e) { var r = stage.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
        stage.addEventListener('pointerdown', function (e) { stage.setPointerCapture(e.pointerId); pts[e.pointerId] = local(e); last = null; pinch = null; });
        stage.addEventListener('pointermove', function (e) {
          if (!pts[e.pointerId]) return; pts[e.pointerId] = local(e);
          var ids = Object.keys(pts);
          if (ids.length >= 2) {
            var a = pts[ids[0]], b = pts[ids[1]], dist = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
            if (pinch) { x += mx - pinch.mx; y += my - pinch.my; zoomTo(pinch.z * dist / pinch.d, mx, my); }
            else pinch = { d: dist, z: z, mx: mx, my: my };
            pinch.mx = mx; pinch.my = my; if (!pinch.d) pinch.d = dist;
            return;
          }
          var p = pts[e.pointerId];
          if (last) { x += p.x - last.x; y += p.y - last.y; draw(); }
          last = p;
        });
        var up = function (e) { delete pts[e.pointerId]; last = null; if (Object.keys(pts).length < 2) pinch = null; };
        stage.addEventListener('pointerup', up); stage.addEventListener('pointercancel', up);
        stage.addEventListener('keydown', function (e) { // 키보드: 화살표로 옮기기, +/- 확대
          var k = e.key; if (k === 'ArrowLeft') x += 10; else if (k === 'ArrowRight') x -= 10; else if (k === 'ArrowUp') y += 10; else if (k === 'ArrowDown') y -= 10;
          else if (k === '+' || k === '=') { zoomTo(z * 1.1); return; } else if (k === '-') { zoomTo(z / 1.1); return; } else return;
          e.preventDefault(); draw();
        });
        stage.tabIndex = 0; stage.setAttribute('aria-label', '사진 위치(화살표로 옮기기, +/- 확대)');
        var done = false;
        function finish(blob, err) { if (done) return; done = true; d.close(); d.remove(); URL.revokeObjectURL(url); if (blob) ok(blob); else no(err || 'cancel'); }
        acts.appendChild(btn('취소', 'btn', function () { finish(null, 'cancel'); }));
        var saveB = acts.appendChild(btn('저장', 'btn btn-primary', function () {
          var c = document.createElement('canvas'); c.width = c.height = size;
          var g = c.getContext('2d'); g.imageSmoothingQuality = 'high';
          var sx = -x / sc, sy = -y / sc, sw = V / sc;
          g.drawImage(img, sx, sy, sw, sw, 0, 0, size, size);
          encodeCanvas(c).then(function (b) { finish(b); }, function () { finish(null, 'encode'); });
        }));
        x0.addEventListener('click', function () { finish(null, 'cancel'); });
        d.addEventListener('cancel', function (e) { e.preventDefault(); finish(null, 'cancel'); });
        draw();
        saveB.autofocus = true;
        if (d.showModal) d.showModal(); else d.setAttribute('open', '');
      };
      img.src = url;
    });
  }
  function openBlocks() {
    var body = dialog('차단한 사용자');
    body.appendChild(el('p', 'muted', '차단한 사람과는 서로 팔로우·쪽지를 할 수 없고, 그 사람의 글은 내 화면에서 숨겨집니다. 상대에게 차단했다는 알림은 가지 않습니다.'));
    var ul = el('ul', 'kw-users'); body.appendChild(ul);
    api('/v1/blocks').then(function (d) {
      if (!(d.items || []).length) { ul.appendChild(el('li', 'muted', '차단한 사용자가 없습니다.')); return; }
      d.items.forEach(function (u) {
        var li = el('li', 'kw-user'); li.appendChild(avatar(u.nick, u.id)); li.appendChild(el('strong', null, u.nick));
        li.appendChild(btn('차단 해제', 'btn btn-small', function () { api('/v1/block', { method: 'POST', body: { uid: u.id } }).then(function (r) { if (!r.blocked) { delete BLOCKED[u.id]; li.remove(); } }); }));
        ul.appendChild(li);
      });
    });
  }
  // 팔로워·팔로잉 목록 창
  function openFollows(uid, type, nick) {
    var body = dialog((nick ? nick + '님의 ' : '') + (type === 'following' ? '팔로잉' : '팔로워'));
    var ul = el('ul', 'kw-users'); body.appendChild(ul);
    var more = btn('더 보기', 'btn btn-small', function () { load(); }); more.hidden = true; body.appendChild(more);
    var before = 0;
    function load() {
      api('/v1/users/' + uid + '/follows?type=' + type + (before ? '&before=' + before : '')).then(function (d) {
        var items = d.items || [];
        if (!items.length && !before) ul.appendChild(el('li', 'muted', type === 'following' ? '아직 팔로우한 사람이 없습니다.' : '아직 팔로워가 없습니다.'));
        items.forEach(function (u) {
          var li = el('li', 'kw-user'); li.appendChild(avatar(u.nick, u.id));
          var who = el('div', 'kw-user-who'), a = el('a', null, u.nick); a.href = profileUrl(u.id); who.appendChild(a);
          if (u.bio) who.appendChild(el('span', 'muted kw-small', u.bio)); li.appendChild(who);
          if (ME && !u.self) {
            var fb = btn(u.following ? '팔로잉' : '팔로우', 'btn btn-small' + (u.following ? '' : ' btn-primary'), function () {
              fb.disabled = true;
              api('/v1/follow', { method: 'POST', body: { uid: u.id } }).then(function (r) { fb.disabled = false; if (r._status !== 200) { if (r.message) alert(r.message); return; } fb.textContent = r.following ? '팔로잉' : '팔로우'; fb.className = 'btn btn-small' + (r.following ? '' : ' btn-primary'); });
            });
            li.appendChild(fb);
          }
          ul.appendChild(li); before = u.created;
        });
        more.hidden = !d.more;
      }).catch(function () { ul.appendChild(el('li', 'muted', '불러오지 못했습니다.')); });
    }
    load();
  }
  function logout() { // 이 기기의 푸시 구독도 함께 끊는다(로그아웃한 기기로 알림이 가지 않게)
    var go = function (ep) { api('/v1/auth/logout', { method: 'POST', body: ep ? { endpoint: ep } : {} }).then(function () { location.reload(); }, function () { location.reload(); }); };
    try {
      if (!('serviceWorker' in navigator) || !window.PushManager) return go('');
      navigator.serviceWorker.getRegistration().then(function (r) { return r && r.pushManager ? r.pushManager.getSubscription() : null; })
        .then(function (s) { if (s) { var ep = s.endpoint; s.unsubscribe().catch(function () {}); go(ep); } else go(''); }, function () { go(''); });
    } catch (e) { go(''); }
  }
  // 가입 직후 "지금 바꾸기"를 눌렀으면 새로 고친 뒤 내 계정 창을 연다
  meReady.then(function () { var k = null; try { k = sessionStorage.getItem('kw_open_acct'); sessionStorage.removeItem('kw_open_acct'); } catch (e) {} if (k && ME) openAccount(); });
  // 로그인에서 돌아왔을 때: 주소의 ?login= 을 지우고, 계정이 없으면 바로 자동 가입한다
  (function () {
    var m = /[?&]login=(ok|fail)/.exec(location.search); if (!m) return;
    var clean = location.pathname + location.search.replace(/([?&])login=\w+&?/, '$1').replace(/[?&]$/, '') + location.hash;
    try { history.replaceState(null, '', clean); } catch (e) {}
    if (m[1] === 'fail') { meReady.then(function () { var b = dialog('로그인하지 못했습니다'); b.appendChild(el('p', null, '잠시 뒤 다시 시도해 주세요.')); }); return; }
    meReady.then(function () { if (LOGGED && !ME) openAccount(); });
  })();
  // 알림 창 아래: 이 기기 푸시가 꺼져 있으면 설정으로 안내(설치한 앱·지원 브라우저에서만)
  function pushPromo(body) {
    try {
      if (!('serviceWorker' in navigator) || !window.PushManager || !window.Notification || Notification.permission === 'denied') return;
      navigator.serviceWorker.getRegistration().then(function (r) { return r && r.pushManager ? r.pushManager.getSubscription() : null; }).then(function (s) {
        if (s) return;
        var a = el('a', 'kw-push-promo', '🔔 휴대폰 알림 켜기 — 팔로우한 종목의 새 리포트를 바로 받아 보세요 →'); a.href = base + '/settings/#push';
        body.appendChild(a);
      }).catch(function () {});
    } catch (e) {}
  }
  function openBell() {
    var body = dialog('알림'); if (window.kwEv) kwEv('notif_open');
    api('/v1/notifications').then(function (d) {
      var items = d.items || [];
      if (!items.length) { body.appendChild(el('p', 'muted', '아직 알림이 없습니다.')); pushPromo(body); return; }
      var ul = el('ul', 'kw-notifs');
      items.forEach(function (x) {
        var li = el('li', x.seen ? '' : 'unread'), a = el('a');
        var t = x.type === 'follow' ? x.from_nick + '님이 나를 팔로우했습니다'
          : x.type === 'reply' ? (x.from_nick || '누군가') + '님' + (x.n > 1 ? ' 등 ' + x.n + '명' : '') + '이 내 글에 답글을 달았습니다'
          : x.type === 'repost' ? (x.from_nick || '누군가') + '님' + (x.n > 1 ? ' 등 ' + x.n + '명' : '') + '이 내 글을 리포스트했습니다'
          : x.type === 'quote' ? (x.from_nick || '누군가') + '님이 내 글을 인용했습니다'
          : x.type === 'mention' ? (x.from_nick || '누군가') + '님이 글에서 나를 언급했습니다'
          : x.type === 'report' ? '새 리포트 · ' + shortTitle(x.from_nick || '')
          : '내 글에 좋아요 ' + x.n + '개';
        a.textContent = t; a.href = x.type === 'follow' ? profileUrl(x.ref) : x.type === 'report' ? base + '/r/' + x.ref + '/' : itemUrl(x.slug, x.ref);
        li.appendChild(a);
        li.appendChild(el('span', 'muted', (x.slug ? ' · ' + threadLabel(x.slug) : '') + ' · ' + ago(x.updated)));
        ul.appendChild(li);
      });
      body.appendChild(ul);
      pushPromo(body);
      api('/v1/notifications/read', { method: 'POST' }).then(function () { UNREAD = 0; paintHeader(); });
    }).catch(function () { body.appendChild(el('p', 'muted', '알림을 불러오지 못했습니다.')); });
  }
  // 휴대폰 아래 탭 줄: 내 정보·알림·글쓰기
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-tab-me],[data-tab-bell],[data-compose]'); if (!t) return;
    e.preventDefault();
    meReady.then(function () {
      if (t.hasAttribute('data-tab-me')) { if (ME) location.href = profileUrl(ME.id); else openAccount(); return; }
      if (t.hasAttribute('data-tab-bell')) { if (ME) openBell(); else openAccount(); return; }
      // 글쓰기: 이 화면에 글 상자(홈 피드·종토방)가 있으면 그리로, 없으면 홈 피드 글쓰기로
      // 글쓰기: 홈은 글 상자로, 리포트·종목 화면은 그 화면의 커뮤니티 글쓰기(리포트 첨부·종목 태그)로, 그 밖은 홈 글쓰기로
      var ta = document.querySelector('[data-composer]:not([hidden]) textarea');
      if (ta) { ta.scrollIntoView({ block: 'center', behavior: 'smooth' }); setTimeout(function () { ta.focus(); }, 300); return; }
      var cc = document.querySelector('[data-community] [data-cmty-compose]');
      if (cc) { cc.click(); return; }
      location.href = base + '/?compose=1';
    });
  });
  (function () { // 지금 화면의 탭 표시
    var p = location.pathname.replace(base, '') || '/';
    document.querySelectorAll('[data-tabbar] a[data-path]').forEach(function (a) { if (a.getAttribute('data-path') === p) a.setAttribute('aria-current', 'page'); });
  })();
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-open-account],[data-open-bell]');
    if (!t) return;
    e.preventDefault();
    if (t.hasAttribute('data-open-bell')) openBell(); else openAccount();
  });

  // ---------- 검색어 기록(검색 페이지) ----------
  var lastLogged = '', logTimer = 0;
  window.kwLogSearch = function (q, hits) {
    clearTimeout(logTimer);
    q = String(q || '').trim();
    if (q.length < 2 || q === lastLogged) return;
    // 결과가 없던 검색어도 따로 센다(어떤 종목 리포트를 원하는지 알 수 있음)
    logTimer = setTimeout(function () { lastLogged = q; if (window.kwEv) kwEv('search'); api('/v1/search', { method: 'POST', body: hits ? { q: q } : { q: q, miss: 1 }, keepalive: true }).catch(function () {}); }, 1500);
  };

  // ---------- 공통: 리포트 목록(search.json)과 조회 순위 ----------
  var idxP = null;
  function loadIndex() {
    if (!idxP) idxP = fetch(base + '/search.json').then(function (r) { return r.json(); }).then(function (idx) {
      var bySlug = {};
      (idx || []).forEach(function (r) { var m = String(r.u).match(/\/r\/([^/]+)\/?$/); if (m) bySlug[m[1]] = r; });
      return { idx: idx || [], bySlug: bySlug };
    });
    return idxP;
  }
  function popular(days) {
    return api('/v1/popular?days=' + days + '&limit=50').then(function (d) { return d.items || []; }).catch(function () { return []; });
  }
  // 오늘 조회가 3 이상이고, 지난 6일 하루 평균의 2배 이상이면 급상승
  function rising(x, days) { var prev = (x.n - (x.today || 0)) / 6; return days === 7 && (x.today || 0) >= 3 && x.today >= prev * 2; }
  function rankList(ol, items, I, days) {
    ol.textContent = '';
    var showN = items.length && items[0].n >= 10; // 숫자가 작을 때는 순위만 보여 준다
    items.forEach(function (x, i) {
      var r = I.bySlug[x.slug], li = el('li', 'rank-item');
      li.appendChild(el('span', 'rank-no', String(i + 1)));
      var a = el('a', 'rank-link'); a.href = r.u;
      a.appendChild(el('span', 'rank-tick', r.k));
      a.appendChild(el('span', 'rank-title', r.t.replace(/^.*?주가 내러티브와 패턴 투자전략:\s*/, '').replace(/^.*?가격 내러티브와 패턴 투자전략:\s*/, '')));
      li.appendChild(a);
      if (rising(x, days)) li.appendChild(el('span', 'rank-hot', '급상승'));
      if (showN) li.appendChild(el('span', 'rank-n muted', '조회 ' + num(x.n)));
      ol.appendChild(li);
    });
  }

  // ---------- 홈: 많이 본 리포트 / 관심 종목 / 테마별 관심도 / 최근 댓글 ----------
  var ins = document.querySelector('[data-insights]');
  if (ins) {
    var norm = function (s) { return String(s || '').toLowerCase().replace(/[\s·\-_.,()]/g, ''); };
    var show = function (sel) { ins.querySelector(sel).hidden = false; ins.hidden = false; };
    Promise.all([loadIndex(), popular(7), popular(1),
      api('/v1/trending?days=7').catch(function () { return {}; }),
      Promise.resolve({}),
      document.querySelector('[data-recent-board]') ? api('/v1/comments/recent?kind=board&limit=10').catch(function () { return {}; }) : Promise.resolve({})
    ]).then(function (res) {
      var I = res[0], keep = function (x) { return I.bySlug[x.slug]; };
      var p7 = res[1].filter(keep), p1 = res[2].filter(keep), tr = res[3] || {};

      // 1) 많이 본 리포트 (오늘 / 7일)
      if (p7.length >= 2) {
        var ol = ins.querySelector('[data-popular-list]');
        var tabs = ins.querySelectorAll('[data-pop-range]');
        var pick = function (days) {
          rankList(ol, (days === 1 ? p1 : p7).slice(0, 5), I, days);
          tabs.forEach(function (t) { t.setAttribute('aria-selected', +t.getAttribute('data-pop-range') === days ? 'true' : 'false'); });
        };
        if (p1.length >= 2) tabs.forEach(function (t) { t.addEventListener('click', function () { pick(+t.getAttribute('data-pop-range')); }); });
        else ins.querySelector('.ins-tabs').hidden = true;
        pick(7);
        show('[data-popular]');
      }

      // 2) 관심 많은 종목: 7일 조회 + 사이트 검색(검색은 의도가 뚜렷해 3배로 셈). 사이트에 있는 종목만
      var tick = {};
      I.idx.forEach(function (r) {
        if (!tick[r.k]) tick[r.k] = { k: r.k, c: r.c, names: [], n: 0 };
        tick[r.k].names = tick[r.k].names.concat([r.k, r.c, r.e].concat(r.a || []).map(norm).filter(function (s) { return s.length >= 2; }));
      });
      p7.forEach(function (x) { var r = I.bySlug[x.slug]; tick[r.k].n += x.n; });
      (tr.items || []).forEach(function (x) {
        var q = norm(x.q);
        Object.keys(tick).forEach(function (k) {
          if (tick[k].names.some(function (nm) { return nm === q || (q.length >= 2 && nm.indexOf(q) === 0); })) tick[k].n += 3 * x.n;
        });
      });
      var hot = Object.keys(tick).map(function (k) { return tick[k]; }).filter(function (t) { return t.n > 0; })
        .sort(function (a, b) { return b.n - a.n; }).slice(0, document.querySelector('[data-explore]') ? 15 : 8);
      if (hot.length >= 2) {
        var ul = ins.querySelector('[data-trending-list]');
        hot.forEach(function (t, i) {
          var li = el('li'), a = el('a', 'chip'); a.href = base + '/t/' + t.k.toLowerCase() + '/';
          a.appendChild(el('strong', null, (i + 1) + ' ' + t.k));
          a.appendChild(document.createTextNode(' ' + t.c));
          li.appendChild(a); ul.appendChild(li);
        });
        show('[data-trending]');
      }

      // 3) 테마별 관심도: 7일 조회를 테마별로 합친 비중. 표본이 작으면(10회 미만) 숨김
      var th = {}, ts = {}, total = 0;
      p7.forEach(function (x) { var r = I.bySlug[x.slug]; if (!r.th) return; ts[r.th] = r.ts; th[r.th] = (th[r.th] || 0) + x.n; total += x.n; });
      var ths = Object.keys(th).map(function (k) { return { name: k, n: th[k] }; }).sort(function (a, b) { return b.n - a.n; }).slice(0, 6);
      if (ths.length >= 2 && total >= 10) {
        var bl = ins.querySelector('[data-theme-list]'), top = ths[0].n;
        ths.forEach(function (t) {
          var li = el('li', 'bar'), pct = Math.round(t.n / total * 100);
          var a = el('a', 'bar-name', t.name); a.href = base + '/theme/' + ts[t.name] + '/';
          var track = el('span', 'bar-track'), fill = el('span', 'bar-fill'); fill.style.width = Math.max(4, t.n / top * 100) + '%';
          track.appendChild(fill);
          li.appendChild(a); li.appendChild(track); li.appendChild(el('span', 'bar-pct', pct + '%'));
          bl.appendChild(li);
        });
        show('[data-themes]');
      }

      // 4) 탐색 화면: 커뮤니티 최근 글(종목 태그 + 글)
      var bl2 = ins.querySelector('[data-recent-board-list]'), rb = (res[5] || {}).items || [];
      if (bl2 && rb.length) {
        rb.forEach(function (c) {
          var li = el('li', 'rc-item'), a = el('a', 'rc-link'); a.href = postUrl(c.id);
          var head = el('span', 'rc-head');
          var btk = /^b-(.+)$/.exec(c.slug || ''); if (btk && btk[1] !== 'talk') head.appendChild(el('span', 'rank-tick', btk[1].toUpperCase()));
          head.appendChild(el('strong', 'rc-nick', c.nick));
          head.appendChild(el('span', 'muted', ago(c.created) + (c.likes ? ' · ♥ ' + num(c.likes) : '')));
          a.appendChild(head); a.appendChild(el('span', 'rc-body', c.body));
          li.appendChild(a); bl2.appendChild(li);
        });
        show('[data-recent-board]');
      }
      var te = ins.querySelector('[data-talk-empty]'); if (te) te.hidden = !!rb.length;
    }).catch(function () {});

  }

  // ---------- 프로필(/u/?id=번호) ----------
  var prof = document.querySelector('[data-profile]');
  if (prof) {
    var pid = (/[?&]id=(\d+)/.exec(location.search) || [])[1];
    var pnick = (/[?&]n=([^&]+)/.exec(location.search) || [])[1];
    var pmsg = prof.querySelector('[data-profile-msg]');
    var pidReady = pid ? Promise.resolve(pid) : pnick ? api('/v1/users/by-nick?n=' + pnick).then(function (d) { return d.id ? String(d.id) : null; }) : Promise.resolve(null);
    pidReady.then(function (id) {
    pid = id;
    if (!pid) { pmsg.textContent = pnick ? '"' + decodeURIComponent(pnick) + '" 닉네임을 쓰는 사람을 찾지 못했습니다.' : '프로필 주소가 올바르지 않습니다.'; return; }
    if (pnick && history.replaceState) { try { history.replaceState(null, '', location.pathname + '?id=' + pid); } catch (e) {} }
    Promise.all([meReady, api('/v1/users/' + pid)]).then(function (res) {
      var d = res[1];
      if (d._status !== 200) { pmsg.textContent = '찾을 수 없는 프로필입니다(탈퇴했거나 이용이 제한된 계정).'; return; }
      prof.textContent = '';
      document.title = d.user.nick + ' | ' + document.title.split('|').pop().trim();
      seedAv(d.user.id, d.user.av);
      var head = el('div', 'profile-head'), av = avatar(d.user.nick, d.user.id); av.className += ' profile-av';
      head.appendChild(av);
      if (d.self) editableAv(av, flash);
      var who = el('div', 'profile-who');
      who.appendChild(el('h1', null, d.user.nick));
      if (d.user.bio) who.appendChild(el('p', 'profile-bio', d.user.bio));
      var since = el('p', 'muted profile-since', new Date(d.user.created).toLocaleDateString('ko-KR') + ' 가입');
      if (d.followsMe && !d.self) since.appendChild(el('span', 'profile-fm', '나를 팔로우함'));
      who.appendChild(since);
      head.appendChild(who);
      prof.appendChild(head);
      var st = el('ul', 'profile-stats');
      [['글', d.stats.posts], ['받은 좋아요', d.stats.likes], ['팔로워', d.stats.followers], ['팔로잉', d.stats.following]].forEach(function (x) {
        var li = el('li'); li.appendChild(el('strong', null, num(x[1]))); li.appendChild(el('span', 'muted', x[0])); st.appendChild(li);
      });
      prof.appendChild(st);
      [2, 3].forEach(function (i) { // 팔로워·팔로잉 수를 누르면 목록
        var li = st.children[i]; li.classList.add('profile-stat-btn'); li.setAttribute('role', 'button'); li.tabIndex = 0;
        var open = function () { openFollows(d.user.id, i === 2 ? 'followers' : 'following', d.user.nick); };
        li.addEventListener('click', open); li.addEventListener('keydown', function (e) { if (e.key === 'Enter') open(); });
      });
      var fcount = st.children[2].querySelector('strong');
      if (d.self) {
        var sacts = el('div', 'profile-acts');
        sacts.appendChild(btn('프로필 편집', 'btn', openAccount));
        var sdm = el('a', 'btn', '쪽지함'); sdm.href = base + '/dm/'; sacts.appendChild(sdm);
        prof.appendChild(sacts);
        // 운영자 계정이면 운영 통계(어드민)로 가는 바로가기를 맨 위에
        api('/v1/admin/whoami').then(function (w) {
          if (!w.owner) return;
          var ad = el('a', 'admin-shortcut');
          ad.href = base + '/admin/';
          ad.appendChild(el('strong', null, '📊 운영 통계 열기'));
          ad.appendChild(el('span', 'muted', '방문·유입 분석 · 신고 처리 · 앱 설치'));
          prof.insertBefore(ad, prof.firstChild);
        }).catch(function () {});
      } else {
        var fb = btn(d.following ? '팔로잉' : '팔로우', 'btn ' + (d.following ? '' : 'btn-primary') + ' follow-btn', function () {
          if (!ME) { openAccount(); return; }
          fb.disabled = true;
          api('/v1/follow', { method: 'POST', body: { uid: d.user.id } }).then(function (r) {
            fb.disabled = false;
            if (r._status !== 200) { if (r.message) alert(r.message); return; }
            fb.textContent = r.following ? '팔로잉' : '팔로우'; if (r.following && window.kwEv) kwEv('follow_user');
            fb.className = 'btn ' + (r.following ? '' : 'btn-primary') + ' follow-btn';
            fcount.textContent = num(r.followers);
          }).catch(function () { fb.disabled = false; });
        });
        fb.setAttribute('aria-pressed', d.following ? 'true' : 'false');
        var acts = el('div', 'profile-acts'); acts.appendChild(fb);
        var dmb = el('a', 'btn', '쪽지'); dmb.href = base + '/dm/?to=' + d.user.id;
        dmb.addEventListener('click', function (e) { if (!ME) { e.preventDefault(); openAccount(); } });
        acts.appendChild(dmb);
        var more = btn('⋯', 'btn profile-more', function () {
          var b2 = dialog(d.user.nick);
          b2.appendChild(btn(BLOCKED[d.user.id] ? '차단 해제' : '차단하기', 'btn', function () {
            if (!ME) { openAccount(); return; }
            if (!BLOCKED[d.user.id] && !confirm(d.user.nick + '님을 차단할까요? 서로 팔로우가 풀리고, 쪽지를 주고받을 수 없으며, 이 사람의 글이 내 화면에서 숨겨집니다.')) return;
            api('/v1/block', { method: 'POST', body: { uid: d.user.id } }).then(function (r) {
              if (r._status !== 200) { alert(r.message || '처리하지 못했습니다.'); return; }
              if (r.blocked) BLOCKED[d.user.id] = 1; else delete BLOCKED[d.user.id];
              if (window.kwEv && r.blocked) kwEv('block');
              dlg.close(); flash(r.blocked ? '차단했습니다' : '차단을 풀었습니다'); setTimeout(function () { location.reload(); }, 600);
            });
          }));
          var rep = function (what, label) { return btn(label, 'btn', function () {
            api('/v1/users/' + d.user.id + '/report', { method: 'POST', body: { what: what } }).then(function () { dlg.close(); flash('신고했습니다. 운영자가 확인합니다'); });
          }); };
          b2.appendChild(btn('프로필 공유', 'btn', function () {
            var su = API + '/s/u/' + d.user.id;
            if (navigator.share) navigator.share({ title: d.user.nick + '님의 프로필 · 김박사 월드', url: su }).catch(function () {});
            else if (navigator.clipboard) navigator.clipboard.writeText(su).then(function () { flash('링크를 복사했습니다'); });
            if (window.kwEv) kwEv('share');
          }));
          if (d.user.av) b2.appendChild(rep('avatar', '프로필 사진 신고'));
          b2.appendChild(rep('profile', '닉네임·소개 신고'));
          b2.appendChild(el('p', 'muted kw-small', '사진은 3명이 신고하면 바로 내려가고, 운영자가 다시 확인합니다.'));
        });
        more.setAttribute('aria-label', '더 보기'); acts.appendChild(more);
        prof.appendChild(acts);
        if (BLOCKED[d.user.id]) prof.appendChild(el('p', 'kw-warn', '내가 차단한 사용자입니다. 이 사람의 글은 피드·댓글에서 숨겨집니다.'));
      }
      // 프로필 탭: 글 · 리포스트 (+ 내 프로필이면 최근 읽음 · 저장함 — 이 둘은 이 기기에만 있음)
      var ul = el('ul', 'rc-list');
      var rpUl = el('ul', 'rc-list');
      (d.reposts || []).forEach(function (x) {
        var li = el('li', 'rc-item'), a = el('a', 'rc-link'), h = el('span', 'rc-head');
        h.appendChild(el('span', 'rp-mark', '↻'));
        if (x.kind === 'r') {
          a.href = reportUrl(x.slug); var tk = el('span', 'rank-tick', ''); h.appendChild(tk); h.appendChild(el('span', 'muted', '리포트 · ' + ago(x.at)));
          var tt = el('span', 'rc-body', '…'); a.appendChild(h); a.appendChild(tt);
          reportTitle(x.slug).then(function (r) { tk.textContent = r.k; tt.textContent = shortTitle(r.t); });
        } else {
          a.href = postUrl(x.post.id); h.appendChild(el('span', 'rank-tick', threadLabel(x.post.slug))); h.appendChild(el('span', 'muted', x.post.nick + ' · ' + ago(x.at)));
          a.appendChild(h); a.appendChild(el('span', 'rc-body', x.post.body));
        }
        li.appendChild(a); rpUl.appendChild(li);
      });
      if (!(d.reposts || []).length) rpUl.appendChild(el('li', 'rc-item muted rc-empty', '아직 리포스트한 글이 없습니다.'));
      if (true) {
        var LS = function (k) { try { return JSON.parse(localStorage.getItem(k) || '[]') || []; } catch (e) { return []; } };
        var tabs = el('div', 'seg-tabs prof-tabs'); tabs.setAttribute('role', 'tablist');
        var panes = {}, tbtn = {};
        var mkPane = function (key, label, n) {
          var b = el('button', null); b.type = 'button'; b.setAttribute('role', 'tab');
          b.appendChild(document.createTextNode(label + ' ')); b.appendChild(el('strong', null, num(n)));
          b.addEventListener('click', function () { show(key); });
          tabs.appendChild(b); tbtn[key] = b;
          var p = el('div', 'prof-pane'); p.setAttribute('role', 'tabpanel'); panes[key] = p; return p;
        };
        var show = function (key) {
          Object.keys(panes).forEach(function (k) { panes[k].hidden = k !== key; tbtn[k].setAttribute('aria-selected', k === key ? 'true' : 'false'); });
          try { sessionStorage.setItem('kw-prof-tab', key); } catch (e) {}
        };
        var reportList = function (pane, key, items, emptyText, removeLabel) {
          pane.textContent = '';
          if (!items.length) { pane.appendChild(el('p', 'muted rc-empty', emptyText)); return; }
          var l = el('ul', 'rc-list hist-list');
          items.forEach(function (x) {
            var li = el('li', 'rc-item hist-item'), a = el('a', 'rc-link'); a.href = x.u;
            var h = el('span', 'rc-head'); h.appendChild(el('span', 'rank-tick', x.k || ''));
            if (x.at) h.appendChild(el('span', 'muted', ago(x.at)));
            a.appendChild(h); a.appendChild(el('span', 'rc-body', String(x.t || '').replace(/^.*?(주가|가격) 내러티브와 패턴 투자전략:\s*/, '')));
            li.appendChild(a);
            var rm = el('button', 'cm-link hist-rm', removeLabel); rm.type = 'button'; rm.setAttribute('aria-label', removeLabel);
            rm.addEventListener('click', function () {
              var all = LS(key).filter(function (y) { return y.u !== x.u; });
              try { localStorage.setItem(key, JSON.stringify(all)); } catch (e) {}
              li.remove(); tbtn[key === 'kw-recent' ? 'read' : 'saved'].querySelector('strong').textContent = num(all.length);
            });
            li.appendChild(rm); l.appendChild(li);
          });
          pane.appendChild(l);
        };
        if (d.self) { // 팔로우한 종목·테마
          var tw = el('section', 'my-topics'); tw.appendChild(el('h2', 'section-title', '팔로우한 종목·테마'));
          var tl = el('ul', 'chip-list'); tw.appendChild(tl);
          tl.appendChild(el('li', 'muted kw-small', '불러오는 중…'));
          prof.appendChild(tw);
          myTopics(true).then(function (items) {
            tl.textContent = '';
            if (!items.length) { tl.appendChild(el('li', 'muted kw-small', '아직 없습니다. 종목·테마 페이지나 리포트 제목 옆의 "+ 팔로우"를 눌러 보세요.')); return; }
            var thName = {}; document.querySelectorAll('.theme-nav a').forEach(function (a) { var m = /\/theme\/([^/]+)\//.exec(a.getAttribute('href')); if (m) thName[m[1]] = a.textContent.trim(); });
            items.forEach(function (x) {
              var li = el('li'), a = el('a', 'chip');
              if (x.kind === 't') { a.href = base + '/t/' + x.key.toLowerCase() + '/'; a.appendChild(el('strong', null, x.key)); var nm = (KW.tk || []).filter(function (t) { return t.c === x.key; })[0]; if (nm) a.appendChild(document.createTextNode(' ' + nm.n)); }
              else { a.href = base + '/theme/' + x.key + '/'; a.textContent = '# ' + (thName[x.key] || x.key); }
              li.appendChild(a); tl.appendChild(li);
            });
          });
        }
        var recent = d.self ? LS('kw-recent') : [], saved = d.self ? LS('kw-saved') : [];
        var pPosts = mkPane('posts', '글', d.items.length);
        var pRp = mkPane('reposts', '리포스트', (d.reposts || []).length); pRp.appendChild(rpUl);
        prof.appendChild(tabs); prof.appendChild(pPosts); prof.appendChild(pRp);
        if (d.self) {
        var pRead = mkPane('read', '최근 읽음', recent.length);
        var pSaved = mkPane('saved', '저장함', saved.length);
        prof.appendChild(pRead); prof.appendChild(pSaved);
        reportList(pRead, 'kw-recent', recent, '아직 읽은 리포트가 없습니다. 리포트를 열면 여기에 쌓입니다.', '기록 지우기');
        reportList(pSaved, 'kw-saved', saved, '저장한 리포트가 없습니다. 리포트의 "저장"을 누르면 여기에 모입니다.', '저장 취소');
        }
        if (recent.length) {
          var clr = el('button', 'cm-link hist-clear', '읽은 기록 모두 지우기'); clr.type = 'button';
          clr.addEventListener('click', function () { if (!confirm('이 기기의 읽은 기록을 모두 지울까요?')) return; try { localStorage.setItem('kw-recent', '[]'); } catch (e) {} reportList(pRead, 'kw-recent', [], '읽은 기록을 지웠습니다.', ''); tbtn.read.querySelector('strong').textContent = '0'; clr.remove(); });
          pRead.appendChild(clr);
        }
        if (d.self) [pRead, pSaved].forEach(function (p) { p.appendChild(el('p', 'muted kw-small hist-note', '읽은 기록과 저장한 리포트는 이 기기(브라우저)에만 저장되고 서버로 보내지 않습니다.')); });
        pPosts.appendChild(ul);
        var last = ''; try { last = sessionStorage.getItem('kw-prof-tab') || ''; } catch (e) {}
        var qt = (/[?&]tab=(read|saved|reposts)/.exec(location.search) || [])[1];
        show(qt || (d.self && panes[last] ? last : 'posts'));
      }
      if (!d.items.length) ul.appendChild(el('li', 'rc-item muted rc-empty', '아직 쓴 글이 없습니다.'));
      d.items.forEach(function (c) {
        var li = el('li', 'rc-item'), a = el('a', 'rc-link'); a.href = itemUrl(c.slug, c.id);
        var h = el('span', 'rc-head');
        h.appendChild(el('span', 'rank-tick', threadLabel(c.slug)));
        h.appendChild(el('span', 'muted', (c.reply ? '답글 · ' : '') + ago(c.created) + (c.likes ? ' · ♥ ' + num(c.likes) : '')));
        a.appendChild(h); a.appendChild(el('span', 'rc-body', c.body));
        if (c.quote) a.appendChild(el('span', 'rc-quote', '❝ ' + c.quote.text));
        li.appendChild(a); ul.appendChild(li);
      });
      // 글이 5개 이상이면 4번째 글 뒤에 광고 하나(쿠팡 상자)
      var pT = document.querySelector('template[data-profile-ad]');
      if (pT && d.items.length >= 5 && ul.children[3]) {
        var pli = el('li', 'rc-item rc-ad'); pli.appendChild(document.importNode(pT.content, true)); ul.children[3].after(pli);
        if (window.kwAdNew) kwAdNew(pli.querySelector('.ad-coupang-products'));
      }
    }).catch(function () { pmsg.textContent = '프로필을 불러오지 못했습니다.'; });
    });
  }

  // ---------- 리포스트·인용 ----------
  // 리포스트: 리포트나 남의 글을 내 프로필과 팔로워의 '팔로잉' 피드로 다시 올린다(계정 필요, 다시 누르면 취소)
  // 인용: 리포트·남의 글의 일부(드래그로 골라도 됨)를 붙여 내 생각과 함께 새 글로 올린다(로그인 없이도 가능)
  function reportUrl(sl) { return base + '/r/' + sl + '/'; }
  function paintRepost(kind, ref, n, on) {
    document.querySelectorAll('[data-repost][data-kind="' + kind + '"][data-ref="' + ref + '"]').forEach(function (b) {
      b.hidden = false; if (on != null) b.setAttribute('aria-pressed', on ? 'true' : 'false');
      var sp = b.querySelector('[data-n]'); if (sp && n != null) sp.textContent = n ? num(n) : '';
    });
  }
  document.querySelectorAll('[data-repost]').forEach(function (b) { b.hidden = false; });
  var titleCache = {};
  function reportTitle(sl) { // 지금 화면의 리포트·카드에서, 없으면 search.json에서
    if (titleCache[sl]) return Promise.resolve(titleCache[sl]);
    var a = document.querySelector('article.report[data-slug="' + sl + '"]');
    if (a) return Promise.resolve(titleCache[sl] = { t: a.getAttribute('data-title'), k: a.getAttribute('data-ticker') });
    return loadIndex().then(function (I) { var r = I.bySlug[sl]; return titleCache[sl] = r ? { t: r.t, k: r.k } : { t: '리포트', k: '' }; }).catch(function () { return { t: '리포트', k: '' }; });
  }
  function shortTitle(t) { return String(t || '').replace(/^.*?(주가|가격) 내러티브와 패턴 투자전략:\s*/, ''); }
  // 인용 상자: 출처(리포트 제목 / 원글 쓴 사람) + 인용한 부분. 누르면 원문의 그 자리로
  function quoteBox(q) {
    var a = el('a', 'quote-box');
    var words = String(q.text).split(' ');
    var frag = words.length > 8 ? encodeURIComponent(words.slice(0, 4).join(' ')) + ',' + encodeURIComponent(words.slice(-4).join(' ')) : encodeURIComponent(q.text);
    a.href = q.kind === 'r' ? reportUrl(q.ref) + (q.text ? '#:~:text=' + frag : '') : postUrl(q.ref);
    var src = el('span', 'quote-src', q.kind === 'r' ? '리포트' : '원글');
    a.appendChild(src);
    if (q.text) a.appendChild(richText(el('span', 'quote-text'), q.text));
    else { // 문장 없이 리포트 통째로 공유: 리포트 카드(제목 + 읽기)
      a.classList.add('quote-report');
      var tt = el('span', 'quote-title', '리포트'); a.appendChild(tt); a.appendChild(el('span', 'quote-go', '리포트 읽기 →'));
      reportTitle(q.ref).then(function (r) { tt.textContent = shortTitle(r.t); });
    }
    if (q.kind === 'r') reportTitle(q.ref).then(function (r) { src.textContent = (r.k ? r.k + ' · ' : '') + (q.text ? shortTitle(r.t) : '김박사 월드 리포트'); });
    return a;
  }
  function doRepost(kind, ref) {
    return meReady.then(function () {
      if (!ME) { openAccount(); return; }
      return api('/v1/repost', { method: 'POST', body: { kind: kind, ref: ref } }).then(function (d) {
        if (d._status !== 200) { alert(d.message || '리포스트하지 못했습니다.'); return; }
        paintRepost(kind, ref, d.count, d.reposted); if (d.reposted && window.kwEv) kwEv('repost');
        flash(d.reposted ? '내 프로필과 팔로워 피드에 리포스트했습니다' : '리포스트를 취소했습니다');
      });
    });
  }
  function flash(t) { var x = document.querySelector('.toast'); if (!x) return; x.textContent = t; x.classList.add('show'); clearTimeout(flash.t); flash.t = setTimeout(function () { x.classList.remove('show'); }, 2000); }
  // 리포스트 버튼: 리포스트 / 인용하기 두 가지를 고르는 작은 창
  function openRepostMenu(b) {
    var kind = b.getAttribute('data-kind'), ref = b.getAttribute('data-ref'), on = b.getAttribute('aria-pressed') === 'true';
    var body = dialog('리포스트');
    var r1 = btn(on ? '리포스트 취소' : '리포스트', 'btn rp-opt', function () { dlg.close(); doRepost(kind, ref); });
    r1.insertBefore(document.createTextNode('↻ '), r1.firstChild);
    body.appendChild(r1);
    body.appendChild(el('p', 'muted kw-small rp-desc', '내 프로필과 나를 팔로우한 사람의 피드에 그대로 다시 올립니다.'));
    var r2 = btn('❝ 인용해서 내 생각 쓰기', 'btn rp-opt', function () {
      var src = String(b.getAttribute('data-quote-src') || '').replace(/\s+/g, ' ').trim();
      openQuote({ kind: kind, ref: ref, text: src.length > 300 ? src.slice(0, 297).replace(/\s\S*$/, '') + '…' : src });
    });
    body.appendChild(r2);
    body.appendChild(el('p', 'muted kw-small rp-desc', '본문에서 문장을 드래그하면 그 부분만 골라 인용할 수 있어요.'));
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-repost]'); if (!b || b.disabled) return;
    e.preventDefault(); openRepostMenu(b);
  });
  // 커뮤니티 글쓰기 창: 인용(문장) · 리포트 공유(문장 없이 리포트 첨부) · 그냥 새 글(종목 태그만). opts: { board, onDone }
  function openQuote(q, opts) {
    opts = opts || {};
    if (!opts.onDone && window.kwCmtyDone) opts.onDone = window.kwCmtyDone; // 리포트·종목 화면: 올린 뒤 그 화면 커뮤니티 목록에 바로
    meReady.then(function () {
      if (LOGGED && !ME) { openAccount(); return; }
      var body = dialog(!q ? '새 글' : q.text ? '인용하기' : '리포트 공유'); if (window.kwEv) kwEv(q ? 'quote_open' : 'compose_open');
      var head = el('div', 'qt-who'); head.appendChild(ME ? avatar(ME.nick, ME.id) : avatar('익')); head.appendChild(el('strong', null, ME ? ME.nick : '익명으로 쓰기'));
      body.appendChild(head);
      var ta = el('textarea', 'qt-body'); ta.rows = 3; ta.maxLength = 500;
      ta.placeholder = !q ? '이 종목에 대한 생각을 나눠 보세요' : q.text ? '이 부분에 대한 내 생각을 써 주세요' : '이 리포트에 대한 생각을 써 주세요';
      body.appendChild(ta);
      if (q) { var pv = quoteBox(q); pv.removeAttribute('href'); pv.classList.add('quote-preview'); body.appendChild(pv); }
      var nick = null;
      if (!ME) { nick = el('input', 'qt-nick'); nick.maxLength = 12; nick.placeholder = '닉네임 (비우면 익명)'; body.appendChild(nick); }
      // 종목 태그: 리포트·종목 화면이면 그 종목이 기본, 지우면 태그 없이(커뮤니티 전체에만)
      var sel = el('select', 'qt-board');
      var TKN = {}; (KW.tk || []).forEach(function (x) { TKN[x.c] = x.n; });
      var add = function (v, label) { var o = el('option', null, label); o.value = v; sel.appendChild(o); };
      var setDefault = function (tk) {
        if (tk && TKN[tk] !== undefined) add('b-' + tk.toLowerCase(), (TKN[tk] || tk) + ' ($' + tk + ')');
        add('b-talk', '종목 태그 없이');
      };
      var bm = /^b-(.+)$/.exec(opts.board || (q && q.slug) || '');
      if (q && q.kind === 'r') reportTitle(q.ref).then(function (r) { setDefault(r.k); });
      else setDefault(bm && bm[1] !== 'talk' ? bm[1].toUpperCase() : '');
      body.appendChild(field('종목 태그', sel));
      var m = el('p', 'kw-msg'); m.setAttribute('role', 'status');
      var started = 0; ta.addEventListener('input', function () { if (!started) started = Date.now(); });
      var go = btn('게시', 'btn btn-primary', function () {
        go.disabled = true; m.textContent = '';
        var b = { slug: sel.value, body: ta.value, nick: nick ? nick.value : '', website: '', t: started ? Date.now() - started : 0 };
        if (q) b.quote = { kind: q.kind, ref: q.ref, text: String(q.text || '').replace(/…$/, '') };
        api('/v1/comments', { method: 'POST', body: b }).then(function (d) {
          go.disabled = false;
          if (!d.ok) { m.textContent = d.message || '올리지 못했습니다.'; return; }
          if (d.status === 'held') { m.textContent = d.message; return; }
          if (window.kwEv) kwEv(q ? 'quote_submit' : 'post_submit');
          if (opts.onDone) { var dd = document.querySelector('dialog.kw-dlg[open]'); if (dd) dd.close(); flash('커뮤니티에 올렸습니다'); opts.onDone(d, b); return; }
          location.href = postUrl(d.id);
        }).catch(function () { go.disabled = false; m.textContent = '올리지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; });
      });
      body.appendChild(go); body.appendChild(m);
      body.appendChild(el('p', 'muted kw-small qt-note', '커뮤니티 피드와 ' + (q && q.kind === 'r' ? '이 리포트 아래' : '종목 화면') + '에 함께 보입니다. 링크·연락처·종목 추천 홍보는 자동으로 가려집니다.'));
      setTimeout(function () { ta.focus(); }, 50);
    });
  }
  // 글자를 드래그해 고르면 작은 줄을 띄운다(리포트 본문·종토방/라운지 글):
  //  ❝ 인용 — 내 글로 인용(피드) · 공유 — 고른 문장 + 그 문장으로 바로 가는 링크(카카오톡·문자 등) · 카드 — 인용 이미지(인스타그램·쓰레드·카톡)
  function textFragment(t) { // 링크를 열면 그 문장으로 내려가 노란색으로 보이게(#:~:text=, 크롬·사파리·삼성 인터넷)
    var enc = function (x) { return encodeURIComponent(x).replace(/-/g, '%2D').replace(/,/g, '%2C').replace(/&/g, '%26'); };
    var w = t.split(' ');
    return '#:~:text=' + (w.length > 12 ? enc(w.slice(0, 6).join(' ')) + ',' + enc(w.slice(-4).join(' ')) : enc(t));
  }
  function quoteLink(q) {
    var u = q.kind === 'r' ? location.origin + base + '/r/' + q.ref + '/' : (API + '/s/p/' + q.ref);
    u += (u.indexOf('?') < 0 ? '?' : '&') + 'utm_source=share&utm_medium=quote';
    return q.kind === 'r' ? u + textFragment(q.text) : u;
  }
  function quoteMeta(q) {
    var art = document.querySelector('article.report[data-slug="' + q.ref + '"]');
    var h1 = document.querySelector('meta[property="og:title"]');
    return {
      ticker: art ? art.getAttribute('data-ticker') : (q.slug && /^b-/.test(q.slug) && q.slug !== 'b-talk' ? q.slug.slice(2).toUpperCase() : ''),
      title: q.kind === 'r' ? ((h1 && h1.content) || document.title) : (q.slug === 'b-talk' ? '커뮤니티' : (q.slug ? '$' + q.slug.slice(2).toUpperCase() + ' 커뮤니티' : '김박사 월드'))
    };
  }
  function shareQuote(q) {
    var m = quoteMeta(q), url = quoteLink(q);
    var text = '“' + q.text + '”\n— ' + (q.kind === 'r' ? (m.ticker ? m.ticker + ' 리포트 · ' : '') + '김박사 월드 무료 리포트' : m.title + ' · 김박사 월드');
    if (window.kwEv) kwEv('quote_share');
    if (navigator.share) { navigator.share({ title: m.title, text: text, url: url }).catch(function () {}); return; }
    var all = text + '\n' + url;
    (navigator.clipboard ? navigator.clipboard.writeText(all) : Promise.reject()).then(function () { flash('인용과 링크를 복사했습니다. 카카오톡에 붙여 넣으세요'); }, function () { prompt('아래 내용을 복사하세요', all); });
  }
  // 인용 카드: 1080×1350(4:5, 인스타그램·쓰레드 피드에 가장 크게 보이는 비율)
  function quoteCard(q) {
    var m = quoteMeta(q), W = 1080, H = 1350, c = document.createElement('canvas'); c.width = W; c.height = H;
    var g = c.getContext('2d'), FF = '"Pretendard","Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",system-ui,sans-serif';
    var grd = g.createLinearGradient(0, 0, 0, H); grd.addColorStop(0, '#0b1220'); grd.addColorStop(1, '#16213a'); g.fillStyle = grd; g.fillRect(0, 0, W, H);
    g.fillStyle = '#f59e0b'; g.font = '900 220px Georgia,serif'; g.fillText('“', 72, 300);
    // 본문: 줄 수에 맞춰 글자 크기를 고른다
    function wrap(text, size) {
      // 띄어쓰기 단위로 줄을 바꾼다(한 단어가 한 줄보다 길 때만 글자 단위)
      g.font = '700 ' + size + 'px ' + FF; var lines = [], line = '', maxw = W - 176;
      text.split(' ').forEach(function (w) {
        var t = line ? line + ' ' + w : w;
        if (g.measureText(t).width <= maxw) { line = t; return; }
        if (line) lines.push(line);
        line = '';
        while (g.measureText(w).width > maxw) { var k = w.length; while (k > 1 && g.measureText(w.slice(0, k)).width > maxw) k--; lines.push(w.slice(0, k)); w = w.slice(k); }
        line = w;
      });
      if (line) lines.push(line); return lines;
    }
    var size = 64, lines = wrap(q.text, size);
    while (lines.length > 9 && size > 40) { size -= 4; lines = wrap(q.text, size); }
    if (lines.length > 11) { lines = lines.slice(0, 11); lines[10] = lines[10].slice(0, -1) + '…'; }
    var lh = size * 1.5, y = 380;
    g.fillStyle = '#f8fafc'; g.font = '700 ' + size + 'px ' + FF;
    lines.forEach(function (ln) { g.fillText(ln, 88, y); y += lh; });
    // 아래: 티커 배지 + 리포트 제목 + 사이트
    var by = H - 300;
    g.fillStyle = 'rgba(255,255,255,.12)'; g.fillRect(88, by - 40, W - 176, 2);
    var x = 88;
    if (m.ticker) {
      g.font = '800 40px ' + FF; var tw = g.measureText(m.ticker).width;
      g.fillStyle = '#f59e0b'; roundRect(g, x, by, tw + 36, 60, 14); g.fill();
      g.fillStyle = '#0b1220'; g.fillText(m.ticker, x + 18, by + 44); x += tw + 56;
    }
    g.fillStyle = '#cbd5e1'; g.font = '600 34px ' + FF;
    var tt = m.title; while (g.measureText(tt).width > W - 88 - x && tt.length > 4) tt = tt.slice(0, -2) + '…';
    g.fillText(tt.replace(/……$/, '…'), x, by + 42);
    g.fillStyle = '#f59e0b'; roundRect(g, 88, H - 168, 470, 76, 38); g.fill();
    g.fillStyle = '#0b1220'; g.font = '800 34px ' + FF; g.fillText(q.kind === 'r' ? '무료 리포트 전문 보기 →' : '대화 이어 보기 →', 120, H - 118);
    g.fillStyle = '#94a3b8'; g.font = '600 32px ' + FF; g.fillText('drkimworld.com', 590, H - 118);
    g.fillStyle = '#64748b'; g.font = '600 28px ' + FF; g.fillText('김박사 월드', W - 88 - g.measureText('김박사 월드').width, 96);
    if (window.kwEv) kwEv('quote_card');
    c.toBlob(function (blob) {
      if (!blob) return;
      var file = new File([blob], 'drkimworld-quote.png', { type: 'image/png' }), url = quoteLink(q);
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        navigator.share({ files: [file], text: '“' + q.text.slice(0, 60) + (q.text.length > 60 ? '…' : '') + '” ' + url }).catch(function () {});
        return;
      }
      var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'drkimworld-quote.png'; document.body.appendChild(a); a.click(); a.remove();
      if (navigator.clipboard) navigator.clipboard.writeText(url).catch(function () {});
      flash('인용 카드를 저장했습니다. 링크도 복사했어요');
    }, 'image/png');
  }
  function roundRect(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
  (function () {
    var bar = el('div', 'quote-bar'); bar.hidden = true; bar.setAttribute('role', 'toolbar'); bar.setAttribute('aria-label', '고른 문장');
    var bQ = el('button', 'qb', '❝ 인용'), bS = el('button', 'qb qb-main', '공유'), bC = el('button', 'qb', '카드');
    [bQ, bS, bC].forEach(function (b) { b.type = 'button'; bar.appendChild(b); });
    document.body.appendChild(bar);
    var cur = null, timer = 0;
    function check() {
      var sel = window.getSelection && getSelection(); cur = null;
      if (!sel || sel.isCollapsed || !sel.rangeCount) { bar.hidden = true; return; }
      var text = String(sel).replace(/\s+/g, ' ').trim();
      var node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentNode);
      if (!node || text.length < 2) { bar.hidden = true; return; }
      var rep = node.closest('article.report .prose'), up = node.closest('.upost-body'), cm = node.closest('.comments.board .cm-body, .pp-replies .cm-body');
      if (rep) cur = { kind: 'r', ref: rep.closest('article.report').getAttribute('data-slug') };
      else if (up) { var art = up.closest('[data-pid]'); cur = { kind: 'p', ref: art.getAttribute('data-pid'), slug: art.getAttribute('data-board') }; }
      else if (cm && cm.closest('[data-cid]')) {
        var th = cm.closest('[data-thread]'), ppost = document.querySelector('[data-post-page] [data-board]');
        cur = { kind: 'p', ref: cm.closest('[data-cid]').getAttribute('data-cid'), slug: th ? th.getAttribute('data-thread') : ppost ? ppost.getAttribute('data-board') : '' };
      }
      if (!cur) { bar.hidden = true; return; }
      cur.text = text.length > 300 ? text.slice(0, 300) : text;
      var r = sel.getRangeAt(0).getBoundingClientRect();
      bar.hidden = false;
      var bw = bar.offsetWidth || 200;
      // 휴대폰은 위에 기본 복사 메뉴가 뜨므로 선택한 글 아래에, PC는 위에
      bar.style.top = ((window.matchMedia && matchMedia('(pointer: coarse)').matches) ? window.scrollY + r.bottom + 14 : Math.max(8, window.scrollY + r.top - 52)) + 'px';
      bar.style.left = Math.min(window.innerWidth - bw - 8, Math.max(8, r.left + r.width / 2 - bw / 2)) + 'px';
    }
    document.addEventListener('selectionchange', function () { clearTimeout(timer); timer = setTimeout(check, 250); });
    bar.addEventListener('mousedown', function (e) { e.preventDefault(); }); // 누르는 순간 선택이 풀리지 않게
    var run = function (fn) { return function () { if (!cur) return; var q = cur; bar.hidden = true; fn(q); }; };
    bQ.addEventListener('click', run(openQuote));
    bS.addEventListener('click', run(shareQuote));
    bC.addEventListener('click', run(quoteCard));
  })();

  // ---------- 종목·테마 팔로우 ----------
  // 팔로우하면: 팔로잉 피드에 그 종목(테마면 그 테마 종목들) 종토방 글이 모이고, 새 리포트가 나오면 알림
  var topicsP = null;
  function myTopics(fresh) {
    if (!topicsP || fresh) topicsP = meReady.then(function () { return ME ? api('/v1/topics').then(function (d) { return d.items || []; }) : []; }).catch(function () { return []; });
    return topicsP;
  }
  // 팔로우한 종목·테마 → 그 종토방 묶음 이름들(b-pltr …)
  function topicBoards(items) {
    var set = {};
    items.forEach(function (x) {
      if (x.kind === 't') set['b-' + x.key.toLowerCase()] = 1;
      else (KW.tk || []).forEach(function (t) { if (t.s === x.key) set['b-' + t.c.toLowerCase()] = 1; });
    });
    return Object.keys(set);
  }
  function paintTopic(kind, key, st) {
    document.querySelectorAll('[data-topic][data-kind="' + kind + '"][data-key="' + key + '"]').forEach(function (b) {
      b.hidden = false; b.setAttribute('aria-pressed', st.following ? 'true' : 'false');
      b.querySelector('[data-topic-label]').textContent = b.hasAttribute('data-topic-mini') ? (st.following ? '팔로잉' : '팔로우') : st.following ? '✓ 팔로잉' : '+ 팔로우';
      var n = b.querySelector('[data-topic-n]'); if (n) n.textContent = st.followers ? num(st.followers) : '';
    });
  }
  // 팔로우 버튼 칠하기: 처음 화면 + 나중에 붙은 카드(피드 더 보기 등)는 KWC.topics(묶음)로 다시 부른다
  function topicsIn(root) {
    var bs = Array.prototype.slice.call((root || document).querySelectorAll('[data-topic]:not([data-tp])')); if (!bs.length) return;
    bs.forEach(function (b) { b.setAttribute('data-tp', '1'); });
    var keys = bs.map(function (b) { return b.getAttribute('data-kind') + ':' + b.getAttribute('data-key'); }).filter(function (x, i, a) { return a.indexOf(x) === i; }).slice(0, 60);
    meReady.then(function () { return api('/v1/topics/stats?keys=' + encodeURIComponent(keys.join(','))); }).then(function (d) {
      Object.keys(d.stats || {}).forEach(function (k) { var i = k.indexOf(':'); paintTopic(k.slice(0, i), k.slice(i + 1), d.stats[k]); });
    }).catch(function () {});
  }
  topicsIn(document);
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-topic]'); if (!b || b.disabled) return;
    e.preventDefault();
    if (b.hasAttribute('data-topic-mini')) document.querySelectorAll('[data-topic-mini][data-key="' + b.getAttribute('data-key') + '"]').forEach(function (x) { x.classList.add('just'); });
    meReady.then(function () {
      if (!ME) { openAccount(); return; }
      var kind = b.getAttribute('data-kind'), key = b.getAttribute('data-key');
      b.disabled = true;
      api('/v1/topics', { method: 'POST', body: { kind: kind, key: key } }).then(function (d) {
        b.disabled = false;
        if (d._status !== 200) { alert(d.message || '팔로우하지 못했습니다.'); return; }
        paintTopic(kind, key, d); myTopics(true); if (d.following && window.kwEv) kwEv('follow_topic');
        flash(d.following ? '팔로우했어요. 새 리포트 알림과 팔로잉 피드에 이 ' + (kind === 't' ? '종목' : '테마') + ' 글이 모입니다' : '팔로우를 취소했습니다');
      }).catch(function () { b.disabled = false; });
    });
  });

  // 홈 피드·글 상세(social.js)가 같이 쓰는 도구
  window.KWC = {
    myTopics: myTopics, topicBoards: topicBoards, topics: topicsIn,
    openCompose: openQuote, loadIndex: loadIndex, quoteBox: quoteBox, reportTitle: reportTitle, shortTitle: shortTitle, reportUrl: reportUrl, paintRepost: paintRepost,
    api: api, el: el, num: num, ago: ago, avatar: avatar, seedAv: seedAv, isBlocked: isBlocked, hideBlocked: hideBlocked, richText: richText, nickEl: nickEl, dialog: dialog, btn: btn, apiBase: API, openFollows: openFollows, dev: DEV, flash: function (t) { flash(t); },
    profileUrl: profileUrl, postUrl: postUrl, threadUrl: threadUrl, threadLabel: threadLabel,
    setHeart: setHeart, meReady: meReady, openAccount: openAccount, openBell: openBell, loginUrl: loginUrl, providerName: function (p) { return PNAME[p] || p; }, state: function () { return { me: ME, logged: LOGGED, providers: PROVIDERS, dmUnread: DMN, dmRequests: DMREQ }; }, setDm: function (n, r) { DMN = n; DMREQ = r; paintHeader(); }, setBlocked: function (uid, on) { if (on) BLOCKED[uid] = 1; else delete BLOCKED[uid]; hideBlocked(); }
  };

  // ---------- 리포트 끝: 지금 많이 보는 리포트(지금 글 제외) ----------
  var nr = document.querySelector('[data-next-reads]');
  if (nr && slug) {
    Promise.all([loadIndex(), popular(7)]).then(function (res) {
      var I = res[0];
      var items = res[1].filter(function (x) { return x.slug !== slug && I.bySlug[x.slug]; }).slice(0, 5);
      if (items.length < 2) return;
      rankList(nr.querySelector('[data-next-list]'), items, I, 7);
      nr.hidden = false;
    }).catch(function () {});
  }
})();
