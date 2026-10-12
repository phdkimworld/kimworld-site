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
  // 닉네임 첫 글자 동그라미(닉네임마다 색이 정해짐)
  function avatar(nick) {
    var n = String(nick || '?'), h = 0;
    for (var i = 0; i < n.length; i++) h = (h * 31 + n.charCodeAt(i)) >>> 0;
    var a = el('span', 'cm-av', n.replace(/^익명#/, '익').charAt(0));
    a.style.background = 'hsl(' + (h % 360) + ' 42% 46%)';
    a.setAttribute('aria-hidden', 'true');
    return a;
  }
  function ago(ms) {
    var s = Math.max(0, (Date.now() - ms) / 1000);
    if (s < 60) return '방금';
    if (s < 3600) return Math.floor(s / 60) + '분 전';
    if (s < 86400) return Math.floor(s / 3600) + '시간 전';
    if (s < 86400 * 30) return Math.floor(s / 86400) + '일 전';
    var d = new Date(ms); return d.getFullYear() + '.' + (d.getMonth() + 1) + '.' + d.getDate();
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
  function threadUrl(sl) {
    var m = /^b-(.+)$/.exec(sl || '');
    return m ? base + '/t/' + m[1] + '/#board' : base + '/r/' + sl + '/#comments';
  }
  function threadLabel(sl) { var m = /^b-(.+)$/.exec(sl || ''); return m ? m[1].toUpperCase() + ' 종토방' : '리포트 댓글'; }
  function profileUrl(uid) { return base + '/u/?id=' + uid; }
  function nickEl(c, cls) {
    if (!c.uid) return el('strong', cls, c.nick);
    var a = el('a', cls + ' cm-nick-link', c.nick); a.href = profileUrl(c.uid); return a;
  }

  // ---------- 계정(계정 키): 이메일·전화 없이 닉네임만. 키는 이 브라우저에만 저장 ----------
  var ME = null, UNREAD = 0, LOGGED = false, PROVIDERS = [];
  var meReady = api('/v1/me').then(function (d) {
    ME = d.user || null; UNREAD = d.unread || 0; LOGGED = !!d.loggedIn; PROVIDERS = d.providers || [];
    paintHeader(); return ME;
  }).catch(function () { return null; });
  function paintHeader() {
    var lab = document.querySelector('[data-account-label]'); if (lab) lab.textContent = ME ? '내 계정' : '로그인';
    var bell = document.querySelector('[data-open-bell]'); if (bell) bell.hidden = !ME;
    var n = document.querySelector('[data-bell-n]');
    if (n) { n.hidden = !UNREAD; n.textContent = UNREAD > 9 ? '9+' : String(UNREAD); }
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
  var PNAME = { google: 'Google로 로그인', kakao: '카카오 로그인' };
  function loginUrl(prov) { return API + '/v1/auth/' + prov + '/start?return=' + encodeURIComponent(location.pathname + location.search.replace(/[?&]login=\w+/, '') + location.hash); }

  function openAccount() {
    meReady.then(function () {
      var msg = el('p', 'kw-msg'); msg.setAttribute('role', 'status');
      if (!LOGGED) { // 로그인 전: 구글·카카오 버튼
        var body = dialog('로그인');
        body.appendChild(el('p', 'muted', '종토방 글쓰기·팔로우·알림은 로그인 후 쓸 수 있습니다. 로그인할 때 이메일·이름·전화번호는 받지 않고, 같은 사람인지 알아보는 회원 번호만 씁니다.'));
        if (!PROVIDERS.length) body.appendChild(el('p', 'kw-warn', '로그인을 준비하고 있습니다. 잠시 뒤 다시 와 주세요.'));
        PROVIDERS.forEach(function (pv) { var a = el('a', 'btn kw-login kw-login-' + pv, PNAME[pv] || pv); a.href = loginUrl(pv); body.appendChild(a); });
        var tl = el('p', 'muted kw-small'); tl.appendChild(document.createTextNode('로그인하면 ')); var ta = el('a', null, '이용약관'); ta.href = base + '/terms/'; ta.target = '_blank'; tl.appendChild(ta); tl.appendChild(document.createTextNode('에 동의한 것으로 봅니다.')); body.appendChild(tl);
        return;
      }
      if (!ME) { // 로그인은 했지만 닉네임을 아직 안 정함
        var body2 = dialog('닉네임 정하기');
        body2.appendChild(el('p', 'muted', '종토방과 댓글에 보일 이름입니다. 나중에 바꿀 수 없습니다.'));
        var nick = el('input'); nick.maxLength = 12; nick.placeholder = '한글·영문·숫자 2~12자'; nick.autocomplete = 'off';
        var bio = el('input'); bio.maxLength = 80; bio.placeholder = '한 줄 소개 (선택)';
        var agree = el('input'); agree.type = 'checkbox';
        var ag = el('label', 'kw-check'); ag.appendChild(agree);
        var agt = el('span'); agt.appendChild(document.createTextNode('이용약관에 동의합니다 ')); var tl2 = el('a', null, '(보기)'); tl2.href = base + '/terms/'; tl2.target = '_blank'; agt.appendChild(tl2); ag.appendChild(agt);
        body2.appendChild(field('닉네임', nick)); body2.appendChild(field('소개', bio)); body2.appendChild(ag);
        body2.appendChild(btn('시작하기', 'btn btn-primary', function () {
          if (!agree.checked) { msg.textContent = '이용약관에 동의해 주세요.'; return; }
          api('/v1/me', { method: 'POST', body: { nick: nick.value.trim(), bio: bio.value } }).then(function (d) {
            if (!d.ok) { msg.textContent = d.message || '만들지 못했습니다.'; return; }
            location.reload();
          }).catch(function () { msg.textContent = '만들지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; });
        }));
        body2.appendChild(msg);
        body2.appendChild(btn('로그아웃', 'cm-link', logout));
        return;
      }
      var body3 = dialog('내 계정');
      var info = el('div', 'kw-me'); info.appendChild(avatar(ME.nick));
      var nm = el('div'); nm.appendChild(el('strong', null, ME.nick)); nm.appendChild(el('span', 'muted', ' · ' + new Date(ME.created).toLocaleDateString('ko-KR') + ' 가입'));
      info.appendChild(nm); body3.appendChild(info);
      var bio2 = el('input'); bio2.maxLength = 80; bio2.value = ME.bio || ''; bio2.placeholder = '한 줄 소개';
      body3.appendChild(field('소개', bio2));
      var row = el('div', 'kw-row');
      row.appendChild(btn('소개 저장', 'btn', function () {
        api('/v1/me', { method: 'POST', body: { bio: bio2.value } }).then(function (d) { msg.textContent = d.ok ? '저장했습니다.' : (d.message || '저장하지 못했습니다.'); if (d.ok) ME.bio = bio2.value; });
      }));
      var pf = el('a', 'btn', '내 프로필'); pf.href = profileUrl(ME.id); row.appendChild(pf);
      row.appendChild(btn('알림', 'btn', openBell));
      body3.appendChild(row); body3.appendChild(msg);
      body3.appendChild(el('hr'));
      body3.appendChild(btn('로그아웃', 'btn', logout));
      body3.appendChild(btn('계정 삭제', 'cm-link kw-danger', function () {
        var all = confirm('계정을 삭제합니다. 내가 쓴 글도 모두 지울까요?\n[확인] 글도 모두 삭제\n[취소] 글은 "탈퇴한 사용자"로 남김');
        if (!confirm('정말 계정을 삭제할까요? 되돌릴 수 없습니다.')) return;
        api('/v1/me/delete', { method: 'POST', body: { all: all } }).then(function () { location.reload(); });
      }));
    });
  }
  function logout() { api('/v1/auth/logout', { method: 'POST' }).then(function () { location.reload(); }, function () { location.reload(); }); }
  // 로그인에서 돌아왔을 때: 주소의 ?login= 을 지우고, 닉네임이 없으면 바로 정하게 한다
  (function () {
    var m = /[?&]login=(ok|fail)/.exec(location.search); if (!m) return;
    var clean = location.pathname + location.search.replace(/([?&])login=\w+&?/, '$1').replace(/[?&]$/, '') + location.hash;
    try { history.replaceState(null, '', clean); } catch (e) {}
    if (m[1] === 'fail') { meReady.then(function () { var b = dialog('로그인하지 못했습니다'); b.appendChild(el('p', null, '잠시 뒤 다시 시도해 주세요.')); }); return; }
    meReady.then(function () { if (LOGGED && !ME) openAccount(); });
  })();
  function openBell() {
    var body = dialog('알림');
    api('/v1/notifications').then(function (d) {
      var items = d.items || [];
      if (!items.length) { body.appendChild(el('p', 'muted', '아직 알림이 없습니다.')); return; }
      var ul = el('ul', 'kw-notifs');
      items.forEach(function (x) {
        var li = el('li', x.seen ? '' : 'unread'), a = el('a');
        var t = x.type === 'follow' ? x.from_nick + '님이 나를 팔로우했습니다'
          : x.type === 'reply' ? (x.from_nick || '누군가') + '님' + (x.n > 1 ? ' 등 ' + x.n + '명' : '') + '이 내 글에 답글을 달았습니다'
          : '내 글에 좋아요 ' + x.n + '개';
        a.textContent = t; a.href = x.type === 'follow' ? profileUrl(x.ref) : threadUrl(x.slug);
        li.appendChild(a);
        li.appendChild(el('span', 'muted', (x.slug ? ' · ' + threadLabel(x.slug) : '') + ' · ' + ago(x.updated)));
        ul.appendChild(li);
      });
      body.appendChild(ul);
      api('/v1/notifications/read', { method: 'POST' }).then(function () { UNREAD = 0; paintHeader(); });
    }).catch(function () { body.appendChild(el('p', 'muted', '알림을 불러오지 못했습니다.')); });
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-open-account],[data-open-bell]');
    if (!t) return;
    e.preventDefault();
    if (t.hasAttribute('data-open-bell')) openBell(); else openAccount();
  });

  // ---------- 댓글·종토방 묶음 ----------
  function initThread(box) {
    var tslug = box.getAttribute('data-thread'), kind = box.getAttribute('data-kind') || 'report';
    var isReport = kind === 'report';
    var listEl = box.querySelector('[data-cm-list]');
    var bestEl = box.querySelector('[data-cm-best]');
    var countEl = box.querySelector('[data-cm-count]');
    var form = box.querySelector('[data-cm-form]');
    var msg = box.querySelector('[data-cm-msg]');
    var lenEl = box.querySelector('[data-cm-len]');
    var sort = isReport ? 'top' : 'new';
    var startedAt = 0;
    var liked = {};
    var noun = isReport ? '댓글' : '글';

    function item(c, isBest, canReply) {
      var li = el('li', 'cm-item' + (isBest ? ' cm-item-best' : '') + (c.parent ? ' cm-reply' : '') + (c.pinned ? ' cm-item-pinned' : ''));
      li.appendChild(avatar(c.nick));
      var main = el('div', 'cm-main'); li.appendChild(main);
      var head = el('div', 'cm-head');
      if (c.pinned) head.appendChild(el('span', 'cm-badge cm-badge-notice', '공지'));
      if (isBest) head.appendChild(el('span', 'cm-badge', 'BEST'));
      head.appendChild(nickEl(c, 'cm-nick'));
      head.appendChild(el('span', 'cm-time muted', ago(c.created)));
      main.appendChild(head);
      main.appendChild(el('p', 'cm-body', c.body));
      var act = el('div', 'cm-act');
      var like = el('button', 'cm-like', '♥ ' + num(c.likes));
      like.type = 'button';
      like.setAttribute('data-cid', c.id);
      like.setAttribute('aria-pressed', liked[c.id] ? 'true' : 'false');
      like.setAttribute('aria-label', '좋아요 ' + c.likes);
      like.disabled = !!c.mine;
      like.addEventListener('click', function () {
        like.disabled = true;
        api('/v1/comments/' + c.id + '/like', { method: 'POST' }).then(function (d) {
          like.disabled = false;
          if (d._status !== 200) { if (d.message) alert(d.message); return; }
          liked[c.id] = d.liked;
          document.querySelectorAll('.cm-like[data-cid="' + c.id + '"]').forEach(function (b) { b.textContent = '♥ ' + num(d.likes); b.setAttribute('aria-pressed', d.liked ? 'true' : 'false'); });
        }).catch(function () { like.disabled = false; });
      });
      act.appendChild(like);
      if (canReply) {
        var rb = el('button', 'cm-link', '답글'); rb.type = 'button';
        rb.addEventListener('click', function () {
          if (!isReport && !ME) { openAccount(); return; }
          openReply(c.parent || c.id, c.nick);
        });
        act.appendChild(rb);
      }
      if (c.mine) {
        var del = el('button', 'cm-link', '삭제'); del.type = 'button';
        del.addEventListener('click', function () {
          if (!confirm('이 ' + noun + '을 삭제할까요?')) return;
          api('/v1/comments/' + c.id + '/delete', { method: 'POST' }).then(load).catch(function () {});
        });
        act.appendChild(del);
      } else if (!c.pinned) {
        var rep = el('button', 'cm-link', '신고'); rep.type = 'button';
        rep.addEventListener('click', function () {
          if (!confirm('이 ' + noun + '을 신고할까요? 신고가 쌓이면 자동으로 가려집니다.')) return;
          api('/v1/comments/' + c.id + '/report', { method: 'POST' }).then(function () { rep.textContent = '신고됨'; rep.disabled = true; }).catch(function () {});
        });
        act.appendChild(rep);
      }
      main.appendChild(act);
      return li;
    }

    // 답글 쓰기: 원래 글의 답글 묶음 아래에 작은 입력 칸을 연다(답글은 한 단계)
    function openReply(rootId, toNick) {
      var old = listEl.querySelector('.cm-reply-form'); if (old) old.remove();
      var wrap = listEl.querySelector('[data-root="' + rootId + '"]'); if (!wrap) return;
      var f = el('form', 'cm-reply-form'), started = 0;
      var t = el('textarea'); t.rows = 2; t.maxLength = 500; t.placeholder = toNick + '님에게 답글'; t.setAttribute('aria-label', '답글 내용');
      t.addEventListener('input', function () { if (!started) started = Date.now(); });
      var row = el('div', 'cm-form-row'), m = el('span', 'cm-msg muted');
      var cancel = el('button', 'cm-link', '취소'); cancel.type = 'button'; cancel.addEventListener('click', function () { f.remove(); });
      var ok = el('button', 'btn btn-primary', '답글 등록'); ok.type = 'submit';
      row.appendChild(m); row.appendChild(cancel); row.appendChild(ok);
      f.appendChild(t); f.appendChild(row);
      f.addEventListener('submit', function (e) {
        e.preventDefault(); ok.disabled = true;
        api('/v1/comments', { method: 'POST', body: { slug: tslug, nick: form.nick.value, body: t.value, website: '', parent: rootId, t: started ? Date.now() - started : 0 } })
          .then(function (d) {
            ok.disabled = false;
            if (!d.ok) { m.textContent = d.message || '등록하지 못했습니다.'; return; }
            if (d.status === 'held') { m.textContent = d.message; return; }
            load().catch(function () {});
          }).catch(function () { ok.disabled = false; m.textContent = '등록하지 못했습니다.'; });
      });
      wrap.appendChild(f); t.focus();
    }

    function load() {
      return api('/v1/comments?slug=' + encodeURIComponent(tslug) + '&sort=' + sort).then(function (d) {
        if (d._status !== 200) return;
        box.hidden = false;
        // 종토방 글쓰기는 계정이 있을 때만
        if (!isReport) { form.hidden = !ME; var na = box.querySelector('[data-need-account]'); if (na) na.hidden = !!ME; }
        liked = {}; (d.liked || []).forEach(function (id) { liked[id] = true; });
        var real = d.comments.filter(function (c) { return !c.pinned; }).length; // 공지는 글 수에서 뺀다
        countEl.textContent = real ? num(real) : '';
        if (isReport) document.querySelectorAll('[data-post-cm]').forEach(function (n) { if (postSlug(n) === tslug) n.textContent = d.comments.length ? num(d.comments.length) : ''; });
        var nickInput = form.querySelector('[name=nick]');
        if (nickInput && !nickInput.value) {
          if (ME) { nickInput.value = ME.nick; nickInput.readOnly = true; nickInput.title = '계정 닉네임'; }
          else nickInput.placeholder = '닉네임 (비우면 ' + d.me + ')';
        }
        var bol = bestEl.querySelector('ol'); bol.textContent = '';
        (d.best || []).forEach(function (c) { bol.appendChild(item(c, true)); });
        bestEl.hidden = !(d.best && d.best.length);
        listEl.textContent = '';
        // 원 글(정렬 순서 유지) 아래에 답글을 시간순으로
        var roots = d.comments.filter(function (c) { return !c.parent; }), kids = {};
        d.comments.filter(function (c) { return c.parent; }).sort(function (a, b) { return a.created - b.created; })
          .forEach(function (c) { (kids[c.parent] = kids[c.parent] || []).push(c); });
        roots.forEach(function (c) {
          var li = item(c, false, true);
          var rw = el('div', 'cm-thread'); rw.setAttribute('data-root', c.id);
          var rs = kids[c.id] || [];
          if (rs.length) {
            var ul = el('ul', 'cm-replies');
            rs.forEach(function (r) { ul.appendChild(item(r, false, true)); });
            rw.appendChild(ul);
          }
          li.querySelector('.cm-main').appendChild(rw);
          listEl.appendChild(li);
        });
        if (!real) listEl.appendChild(el('li', 'cm-empty muted', isReport ? '첫 댓글을 남겨 주세요.' : '아직 글이 없습니다. 첫 글을 남겨 보세요.'));
        d.roots = roots;
        placeAds();
        if (isReport && sort === 'top') renderTop(d);
      });
    }

    // 대화 사이 광고: 글이 first개를 넘으면 first번째 글 뒤부터 every개마다, 최대 max개(마지막 글 뒤에는 넣지 않음)
    var adTpl = box.querySelector('template[data-thread-ad]'), usedGroups = {};
    function placeAds() {
      if (!adTpl) return;
      var first = +box.getAttribute('data-ad-first') || 8, every = +box.getAttribute('data-ad-every') || 8, max = +box.getAttribute('data-ad-max') || 0;
      var items = Array.prototype.slice.call(listEl.children).filter(function (x) { return x.classList.contains('cm-item'); });
      usedGroups = {};
      for (var i = first, k = 0; i < items.length && k < max; i += every, k++) {
        var frag = document.importNode(adTpl.content, true);
        var li = el('li', 'cm-ad'); li.appendChild(frag);
        // 쿠팡 상자: 광고마다 다른 상품 묶음
        var gs = li.querySelectorAll('[data-cp-group]');
        if (gs.length) {
          var free = []; for (var g = 0; g < gs.length; g++) if (!usedGroups[g]) free.push(g);
          if (!free.length) break;
          var pick = free[Math.floor(Math.random() * free.length)]; usedGroups[pick] = 1;
          for (g = 0; g < gs.length; g++) gs[g].hidden = g !== pick;
          var note = li.querySelector('[data-cp-note]'), dd = gs[pick].getAttribute('data-cp-date');
          if (note) { note.hidden = !dd; var sp = note.querySelector('span'); if (sp) sp.textContent = dd || ''; }
        }
        items[i - 1].after(li);
        if (li.querySelector('ins.adsbygoogle')) { try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {} }
      }
    }

    // (리포트만) 요약 바로 아래 '인기 댓글': 베스트 → 좋아요 받은 댓글 많은 순 2개 → 없으면 최근 댓글 1개
    var topEl = isReport ? document.querySelector('[data-cm-top]') : null;
    function renderTop(d) {
      if (!topEl) return;
      var seen = {};
      var picks = (d.best || []).concat(d.roots.filter(function (c) { return c.likes > 0; }))
        .filter(function (c) { if (seen[c.id]) return false; seen[c.id] = 1; return true; }).slice(0, 2);
      var hot = picks.length > 0;
      if (!hot) picks = d.roots.slice(0, 1);
      topEl.querySelector('.cm-top-title').textContent = hot ? '인기 댓글' : '최근 댓글';
      var ol = topEl.querySelector('ol'); ol.textContent = '';
      var bestIds = (d.best || []).map(function (b) { return b.id; });
      picks.forEach(function (c) { ol.appendChild(item(c, bestIds.indexOf(c.id) >= 0)); });
      var more = topEl.querySelector('[data-cm-more]');
      if (more) more.textContent = '댓글 ' + num(d.comments.length) + '개 모두 보기 · 쓰기';
      topEl.hidden = !picks.length;
    }

    box.querySelectorAll('[data-sort]').forEach(function (b) {
      b.addEventListener('click', function () {
        sort = b.getAttribute('data-sort');
        box.querySelectorAll('[data-sort]').forEach(function (x) { x.setAttribute('aria-selected', x === b ? 'true' : 'false'); });
        load().catch(function () {});
      });
    });
    var ta = form.querySelector('textarea');
    ta.addEventListener('input', function () { if (!startedAt) startedAt = Date.now(); lenEl.textContent = ta.value.length + '/500'; });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn2 = form.querySelector('[type=submit]'); btn2.disabled = true; msg.textContent = '';
      api('/v1/comments', { method: 'POST', body: {
        slug: tslug, nick: form.nick.value, body: ta.value, website: form.website.value,
        t: startedAt ? Date.now() - startedAt : 0
      } }).then(function (d) {
        btn2.disabled = false;
        if (d.error === 'account') { openAccount(); return; }
        if (!d.ok) { msg.textContent = d.message || '등록하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; return; }
        ta.value = ''; lenEl.textContent = '0/500'; startedAt = 0;
        msg.textContent = d.status === 'held' ? d.message : '등록했습니다.';
        sort = 'new';
        box.querySelectorAll('[data-sort]').forEach(function (x) { x.setAttribute('aria-selected', x.getAttribute('data-sort') === 'new' ? 'true' : 'false'); });
        load().catch(function () {});
      }).catch(function () { btn2.disabled = false; msg.textContent = '등록하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; });
    });

    // 첫 화면을 다 그린 뒤 불러온다(본문 표시를 늦추지 않게). 주소가 이 묶음을 가리키면 바로
    var here = location.hash === '#' + box.id;
    var go = function () { meReady.then(load).then(function () { if (location.hash === '#' + box.id) box.scrollIntoView(); }).catch(function () {}); };
    if (here || !isReport) go(); else setTimeout(go, 300);
  }
  document.querySelectorAll('[data-comments]').forEach(initThread);

  // ---------- 리포트: 이 종목 종토방 미리보기(최신 글 3개) ----------
  var peek = document.querySelector('[data-board-peek]');
  if (peek) {
    api('/v1/comments?slug=' + peek.getAttribute('data-board-peek') + '&sort=new').then(function (d) {
      var all = (d.comments || []).filter(function (c) { return !c.pinned; });
      var roots = all.filter(function (c) { return !c.parent; });
      var n = peek.querySelector('[data-board-n]'); if (n && all.length) n.textContent = ' · 글 ' + num(all.length);
      if (!roots.length) return;
      peek.querySelector('[data-board-empty]').hidden = true;
      var ol = peek.querySelector('[data-board-list]');
      roots.slice(0, 3).forEach(function (c) {
        var li = el('li', 'cm-item'); li.appendChild(avatar(c.nick));
        var main = el('div', 'cm-main'), head = el('div', 'cm-head');
        head.appendChild(nickEl(c, 'cm-nick')); head.appendChild(el('span', 'cm-time muted', ago(c.created)));
        if (c.likes) head.appendChild(el('span', 'muted', '♥ ' + num(c.likes)));
        main.appendChild(head); main.appendChild(el('p', 'cm-body board-peek-body', c.body));
        li.appendChild(main); ol.appendChild(li);
      });
    }).catch(function () {});
  }

  // ---------- 검색어 기록(검색 페이지) ----------
  var lastLogged = '', logTimer = 0;
  window.kwLogSearch = function (q, hits) {
    clearTimeout(logTimer);
    q = String(q || '').trim();
    if (q.length < 2 || !hits || q === lastLogged) return;
    logTimer = setTimeout(function () { lastLogged = q; api('/v1/search', { method: 'POST', body: { q: q }, keepalive: true }).catch(function () {}); }, 1500);
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
      api('/v1/comments/recent?limit=5').catch(function () { return {}; })
    ]).then(function (res) {
      var I = res[0], keep = function (x) { return I.bySlug[x.slug]; };
      var p7 = res[1].filter(keep), p1 = res[2].filter(keep), tr = res[3] || {}, rc = (res[4] || {}).items || [];

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
        .sort(function (a, b) { return b.n - a.n; }).slice(0, 8);
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

      // 4) 최근 댓글
      var rcs = rc.filter(keep);
      if (rcs.length) {
        var cl = ins.querySelector('[data-recent-cm-list]');
        rcs.forEach(function (c) {
          var r = I.bySlug[c.slug], li = el('li', 'rc-item'), a = el('a', 'rc-link'); a.href = r.u + '#comments';
          var head = el('span', 'rc-head');
          head.appendChild(el('span', 'rank-tick', r.k));
          head.appendChild(el('strong', 'rc-nick', c.nick));
          head.appendChild(el('span', 'muted', ago(c.created) + (c.likes ? ' · ♥ ' + num(c.likes) : '')));
          a.appendChild(head); a.appendChild(el('span', 'rc-body', c.body));
          li.appendChild(a); cl.appendChild(li);
        });
        show('[data-recent-cm]');
      }
    }).catch(function () {});

    // 5) 종토방 새 글, 6) 팔로잉 소식(계정이 있을 때)
    var rcRender = function (ul, items) {
      items.forEach(function (c) {
        var bm = /^b-(.+)$/.exec(c.slug), li = el('li', 'rc-item'), a = el('a', 'rc-link');
        a.href = threadUrl(c.slug);
        var head = el('span', 'rc-head');
        head.appendChild(el('span', 'rank-tick', bm ? bm[1].toUpperCase() : (c.slug.split('-')[0] || '').toUpperCase()));
        head.appendChild(el('strong', 'rc-nick', c.nick));
        head.appendChild(el('span', 'muted', ago(c.created) + (c.likes ? ' · ♥ ' + num(c.likes) : '')));
        a.appendChild(head); a.appendChild(el('span', 'rc-body', c.body));
        li.appendChild(a); ul.appendChild(li);
      });
    };
    api('/v1/comments/recent?kind=board&limit=5').then(function (d) {
      if (!(d.items || []).length) return;
      rcRender(ins.querySelector('[data-board-latest-list]'), d.items);
      ins.querySelector('[data-board-latest]').hidden = false; ins.hidden = false;
    }).catch(function () {});
    meReady.then(function (me) {
      if (!me) return null;
      return api('/v1/feed/following').then(function (d) {
        if (!(d.items || []).length) return;
        rcRender(ins.querySelector('[data-following-list]'), d.items.slice(0, 6));
        ins.querySelector('[data-following]').hidden = false; ins.hidden = false;
      });
    }).catch(function () {});
  }

  // ---------- 프로필(/u/?id=번호) ----------
  var prof = document.querySelector('[data-profile]');
  if (prof) {
    var pid = (/[?&]id=(\d+)/.exec(location.search) || [])[1];
    var pmsg = prof.querySelector('[data-profile-msg]');
    if (!pid) pmsg.textContent = '프로필 주소가 올바르지 않습니다.';
    else Promise.all([meReady, api('/v1/users/' + pid)]).then(function (res) {
      var d = res[1];
      if (d._status !== 200) { pmsg.textContent = '찾을 수 없는 프로필입니다(탈퇴했거나 이용이 제한된 계정).'; return; }
      prof.textContent = '';
      document.title = d.user.nick + ' | ' + document.title.split('|').pop().trim();
      var head = el('div', 'profile-head'), av = avatar(d.user.nick); av.className += ' profile-av';
      head.appendChild(av);
      var who = el('div', 'profile-who');
      who.appendChild(el('h1', null, d.user.nick));
      if (d.user.bio) who.appendChild(el('p', 'profile-bio', d.user.bio));
      who.appendChild(el('p', 'muted profile-since', new Date(d.user.created).toLocaleDateString('ko-KR') + ' 가입'));
      head.appendChild(who);
      prof.appendChild(head);
      var st = el('ul', 'profile-stats');
      [['글', d.stats.posts], ['받은 좋아요', d.stats.likes], ['팔로워', d.stats.followers], ['팔로잉', d.stats.following]].forEach(function (x) {
        var li = el('li'); li.appendChild(el('strong', null, num(x[1]))); li.appendChild(el('span', 'muted', x[0])); st.appendChild(li);
      });
      prof.appendChild(st);
      var fcount = st.children[2].querySelector('strong');
      if (d.self) {
        prof.appendChild(btn('내 계정 설정', 'btn', openAccount));
      } else {
        var fb = btn(d.following ? '팔로잉' : '팔로우', 'btn ' + (d.following ? '' : 'btn-primary') + ' follow-btn', function () {
          if (!ME) { openAccount(); return; }
          fb.disabled = true;
          api('/v1/follow', { method: 'POST', body: { uid: d.user.id } }).then(function (r) {
            fb.disabled = false;
            if (r._status !== 200) { if (r.message) alert(r.message); return; }
            fb.textContent = r.following ? '팔로잉' : '팔로우';
            fb.className = 'btn ' + (r.following ? '' : 'btn-primary') + ' follow-btn';
            fcount.textContent = num(r.followers);
          }).catch(function () { fb.disabled = false; });
        });
        fb.setAttribute('aria-pressed', d.following ? 'true' : 'false');
        prof.appendChild(fb);
      }
      prof.appendChild(el('h2', 'section-title profile-h', '최근 글'));
      var ul = el('ul', 'rc-list');
      if (!d.items.length) ul.appendChild(el('li', 'rc-item muted rc-empty', '아직 쓴 글이 없습니다.'));
      d.items.forEach(function (c) {
        var li = el('li', 'rc-item'), a = el('a', 'rc-link'); a.href = threadUrl(c.slug);
        var h = el('span', 'rc-head');
        h.appendChild(el('span', 'rank-tick', threadLabel(c.slug)));
        h.appendChild(el('span', 'muted', (c.reply ? '답글 · ' : '') + ago(c.created) + (c.likes ? ' · ♥ ' + num(c.likes) : '')));
        a.appendChild(h); a.appendChild(el('span', 'rc-body', c.body));
        li.appendChild(a); ul.appendChild(li);
      });
      prof.appendChild(ul);
    }).catch(function () { pmsg.textContent = '프로필을 불러오지 못했습니다.'; });
  }

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
