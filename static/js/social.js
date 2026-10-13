// 홈 피드(쓰레드·트위터식)와 글 상세(/p/?id=번호)
// · 홈: '추천'(모든 종토방·라운지 글) / '팔로잉'(내가 팔로우한 사람 + 내 글) 탭. 김박사 월드 리포트(메인 포스트)는 두 탭 모두에 섞여 나온다.
// · 글은 시간순으로 리포트 사이에 끼워 넣되, 리포트 사이 한 칸에 3개까지만(리포트가 글에 묻히지 않게).
// · 새 글 알림 줄: 화면을 보고 있을 때만 1분마다 개수만 묻는다(최대 30번).
(function () {
  var C = window.KWC; if (!C) return;
  var api = C.api, el = C.el, num = C.num, ago = C.ago, base = (window.KW || {}).base || '';
  var SVG = {
    heart: 'M12 20.5s-7.5-4.6-9.3-9.2C1.4 7.9 3.6 4.5 7 4.5c2 0 3.6 1.1 5 3 1.4-1.9 3-3 5-3 3.4 0 5.6 3.4 4.3 6.8-1.8 4.6-9.3 9.2-9.3 9.2z',
    comment: 'M20.5 11.6c0 4.2-3.8 7.4-8.5 7.4-1.2 0-2.4-.2-3.4-.6L4 20l1.2-3.6C4 15.1 3.5 13.4 3.5 11.6 3.5 7.4 7.3 4.2 12 4.2s8.5 3.2 8.5 7.4z',
    share: 'M12 15V3.5M7.5 8 12 3.5 16.5 8M5 12.5v6.2c0 .9.7 1.6 1.6 1.6h10.8c.9 0 1.6-.7 1.6-1.6v-6.2',
    more: 'M5 12h.01M12 12h.01M19 12h.01',
    repost: 'm17 2.5 3 3-3 3M3.5 11V9.5a4 4 0 0 1 4-4H20M7 21.5l-3-3 3-3M20.5 13v1.5a4 4 0 0 1-4 4H4'
  };
  function icon(name) {
    var ns = 'http://www.w3.org/2000/svg', s = document.createElementNS(ns, 'svg');
    s.setAttribute('class', 'ic'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('width', '20'); s.setAttribute('height', '20'); s.setAttribute('aria-hidden', 'true');
    var p = document.createElementNS(ns, 'path'); p.setAttribute('d', SVG[name]); if (name === 'more') p.setAttribute('stroke-width', '3'); s.appendChild(p);
    return s;
  }
  function boardOf(slug) { var m = /^b-(.+)$/.exec(slug || ''); return m && m[1] !== 'talk' ? m[1].toUpperCase() : ''; }
  function toast(t) { var x = document.querySelector('.toast'); if (!x) return; x.textContent = t; x.classList.add('show'); setTimeout(function () { x.classList.remove('show'); }, 1800); }
  // 팔로우처럼 계정이 꼭 필요한 일만 로그인 창을 연다(글·답글은 익명으로도 쓸 수 있다)
  function needLogin() {
    var s = C.state();
    if (s.me) return false;
    C.openAccount(); return true;
  }
  // 로그인했지만 닉네임을 아직 안 정한 경우에만 글쓰기 전에 닉네임 창을 연다
  function needNick() { var s = C.state(); if (s.logged && !s.me) { C.openAccount(); return true; } return false; }
  function share(url, title) {
    var u = location.origin + url;
    if (navigator.share) { navigator.share({ title: title, url: u }).catch(function () {}); return; }
    (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(function () { toast('주소를 복사했습니다'); }, function () { prompt('주소를 복사하세요', u); });
  }

  // ---------- 글 카드(피드·글 상세 공통) ----------
  function postCard(c, opt) {
    opt = opt || {};
    var art = el('article', 'card post upost' + (opt.detail ? ' upost-detail' : '')); art.setAttribute('data-pid', c.id); art.setAttribute('data-board', c.slug || '');
    if (c.rp) { // 팔로우한 사람이 리포스트한 글
      var rpl = el('a', 'rp-line'); rpl.href = C.profileUrl(c.rp.uid); rpl.textContent = '↻ ' + c.rp.nick + '님이 리포스트함'; art.appendChild(rpl);
    }
    var head = el('header', 'post-head');
    var av = C.avatar(c.nick, c.uid); av.className += ' post-av'; head.appendChild(av);
    if (c.uid) { art.setAttribute('data-by-uid', c.uid); if (C.isBlocked(c.uid)) art.hidden = true; }
    var who = el('div', 'post-who');
    who.appendChild(C.nickEl(c, 'post-name'));
    var tk = boardOf(c.slug);
    if (tk) { var ta = el('a', 'tick', tk); ta.href = base + '/t/' + tk.toLowerCase() + '/#board'; ta.title = tk + ' 종토방'; who.appendChild(ta); }
    else who.appendChild(el('span', 'post-lounge', '라운지'));
    var tm = el(opt.detail ? 'span' : 'a', 'post-time muted', '· ' + ago(c.created));
    if (!opt.detail) tm.href = C.postUrl(c.id);
    tm.title = new Date(c.created).toLocaleString('ko-KR');
    who.appendChild(tm);
    head.appendChild(who);
    art.appendChild(head);
    var body = C.richText(el('p', 'upost-body'), c.body);
    art.appendChild(body);
    if (c.quote) { var qb = C.quoteBox(c.quote); qb.classList.add('upost-quote'); art.appendChild(qb); }
    // 두 번 톡톡 누르면 좋아요(쓰레드·인스타그램처럼), 한 번 누르면 글 상세로(링크·이름을 누른 경우는 제외)
    function dblLike() {
      var burst = el('span', 'heart-burst'); burst.setAttribute('aria-hidden', 'true'); burst.appendChild(icon('heart'));
      art.appendChild(burst); setTimeout(function () { burst.remove(); }, 800);
      if (!lk.disabled && lk.getAttribute('aria-pressed') !== 'true') lk.click();
    }
    if (!opt.detail) {
      var tapT = 0;
      body.addEventListener('click', function (e) {
        if (e.target.closest('a') || (window.getSelection && String(getSelection()))) return;
        if (tapT) { clearTimeout(tapT); tapT = 0; dblLike(); return; }
        tapT = setTimeout(function () { tapT = 0; location.href = C.postUrl(c.id); }, 280);
      });
    } else body.addEventListener('dblclick', dblLike);
    var act = el('footer', 'post-actions');
    var rp = el('a', 'pa'); rp.href = C.postUrl(c.id) + '#reply'; rp.setAttribute('aria-label', '답글');
    rp.appendChild(icon('comment')); rp.appendChild(el('span', null, c.replies ? num(c.replies) : ''));
    var lk = el('button', 'pa pa-like'); lk.type = 'button'; lk.setAttribute('aria-label', '좋아요');
    lk.setAttribute('aria-pressed', c.liked ? 'true' : 'false'); lk.appendChild(icon('heart'));
    var ln = el('span', null, c.likes ? num(c.likes) : ''); lk.appendChild(ln);
    if (c.mine) { lk.disabled = true; lk.title = '내 글'; }
    lk.addEventListener('click', function () {
      var on = lk.getAttribute('aria-pressed') !== 'true';
      lk.classList.remove('pop'); void lk.offsetWidth; if (on) lk.classList.add('pop');
      lk.disabled = true;
      api('/v1/comments/' + c.id + '/like', { method: 'POST' }).then(function (d) {
        lk.disabled = false;
        if (d._status !== 200) { if (d.message) toast(d.message); return; }
        lk.setAttribute('aria-pressed', d.liked ? 'true' : 'false'); ln.textContent = d.likes ? num(d.likes) : '';
      }).catch(function () { lk.disabled = false; });
    });
    act.appendChild(lk); act.appendChild(rp); // 하트 왼쪽, 답글 오른쪽(리포트 카드와 같은 순서)
    // 리포스트·인용(누르면 고르는 창). 내 글은 리포스트할 수 없다
    var rb = el('button', 'pa pa-repost'); rb.type = 'button'; rb.setAttribute('aria-label', '리포스트·인용');
    rb.setAttribute('data-repost', ''); rb.setAttribute('data-kind', 'p'); rb.setAttribute('data-ref', c.id); rb.setAttribute('data-quote-src', c.body);
    rb.setAttribute('aria-pressed', c.reposted ? 'true' : 'false'); rb.appendChild(icon('repost'));
    var rn = el('span', null, c.reposts ? num(c.reposts) : ''); rn.setAttribute('data-n', ''); rb.appendChild(rn);
    if (c.mine) { rb.disabled = true; rb.title = '내 글'; }
    act.appendChild(rb);
    var sh = el('button', 'pa pa-share'); sh.type = 'button'; sh.setAttribute('aria-label', '공유'); sh.appendChild(icon('share'));
    sh.addEventListener('click', function () { share(C.postUrl(c.id), c.nick + '님의 글 · 김박사 월드'); });
    act.appendChild(sh);
    var mo = el('button', 'pa pa-more'); mo.type = 'button'; mo.setAttribute('aria-label', '더 보기'); mo.appendChild(icon('more'));
    mo.addEventListener('click', function () {
      var old = art.querySelector('.post-menu'); if (old) { old.remove(); return; }
      var menu = el('div', 'post-menu');
      if (c.mine) menu.appendChild(menuBtn('삭제', function () {
        if (!confirm('이 글을 삭제할까요?')) return;
        api('/v1/comments/' + c.id + '/delete', { method: 'POST' }).then(function (d) { if (d.ok) { if (opt.onDelete) opt.onDelete(); else art.remove(); } });
      }));
      else menu.appendChild(menuBtn('신고', function () {
        if (!confirm('이 글을 신고할까요? 신고가 쌓이면 자동으로 가려집니다.')) return;
        api('/v1/comments/' + c.id + '/report', { method: 'POST' }).then(function () { toast('신고했습니다'); menu.remove(); });
      }));
      if (tk) { var bl = el('a', 'post-menu-i', tk + ' 종토방 가기'); bl.href = base + '/t/' + tk.toLowerCase() + '/#board'; menu.appendChild(bl); }
      if (c.uid) { var pl = el('a', 'post-menu-i', c.nick + '님 프로필'); pl.href = C.profileUrl(c.uid); menu.appendChild(pl); }
      act.after(menu);
    });
    act.appendChild(mo);
    art.appendChild(act);
    // 대표 답글 미리보기(쓰레드처럼 글 아래 한 줄)
    if (c.top && !opt.detail) {
      var tr = el('a', 'upost-reply'); tr.href = C.postUrl(c.id) + '#reply';
      var ra = C.avatar(c.top.nick, c.top.uid); ra.className += ' upost-reply-av'; tr.appendChild(ra);
      var tx = el('span', 'upost-reply-tx'); tx.appendChild(el('strong', null, c.top.nick + ' ')); tx.appendChild(document.createTextNode(c.top.body)); tr.appendChild(tx);
      if (c.replies > 1) tr.appendChild(el('span', 'upost-reply-more', '답글 ' + num(c.replies) + '개 모두 보기'));
      art.appendChild(tr);
    }
    return art;
  }
  function menuBtn(t, fn) { var b = el('button', 'post-menu-i', t); b.type = 'button'; b.addEventListener('click', fn); return b; }

  // ---------- 팔로우 추천 ----------
  function followBtn(u, onDone) {
    var b = el('button', 'btn btn-primary sg-follow', '팔로우'); b.type = 'button';
    b.addEventListener('click', function () {
      if (needLogin()) return;
      b.disabled = true;
      api('/v1/follow', { method: 'POST', body: { uid: u.id } }).then(function (r) {
        b.disabled = false;
        if (r._status !== 200) { if (r.message) toast(r.message); return; }
        b.textContent = r.following ? '팔로잉' : '팔로우'; if (r.following && window.kwEv) kwEv('follow_user');
        b.className = 'btn sg-follow' + (r.following ? '' : ' btn-primary');
        if (onDone) onDone(r.following);
      }).catch(function () { b.disabled = false; });
    });
    return b;
  }
  function suggestList(ul, items) {
    ul.textContent = '';
    items.forEach(function (u) {
      var li = el('li', 'sg-item'); li.appendChild(C.avatar(u.nick, u.id));
      var who = el('div', 'sg-who'); var a = el('a', 'sg-nick', u.nick); a.href = C.profileUrl(u.id); who.appendChild(a);
      who.appendChild(el('span', 'muted sg-sub', u.bio || ('글 ' + num(u.posts) + ' · 받은 좋아요 ' + num(u.likes))));
      li.appendChild(who); li.appendChild(followBtn(u, function (on) { if (on && feed) feed.dirty = true; }));
      ul.appendChild(li);
    });
  }
  var sgBox = document.querySelector('[data-suggest]'), sgItems = null;
  function loadSuggest() {
    return api('/v1/users/suggest').then(function (d) { sgItems = d.items || []; return sgItems; }).catch(function () { return []; });
  }

  // ---------- 홈 피드 ----------
  var feedEl = document.querySelector('[data-feed]'), feed = null;
  if (feedEl) {
    var list = feedEl.querySelector('.feed-list');
    var tabsEl = feedEl.querySelector('[data-feed-tabs]');
    var newBtn = feedEl.querySelector('[data-feed-new]');
    var endEl = feedEl.querySelector('[data-feed-end]'), moreBtn = feedEl.querySelector('[data-feed-more]');
    var tab = 'all';
    try { if (localStorage.getItem('kw-tab') === 'following') tab = 'following'; } catch (e) {}
    feed = { dirty: false };
    var oldest = 0, newest = 0, pollN = 0, loading = false, hotMode = false, loaded = 0, boardsQ = '';
    // 리포트 카드(메인 포스트)와 그 날짜(한국 시간 오전 9시로 본다)
    function reports() {
      return Array.prototype.slice.call(list ? list.querySelectorAll(':scope > article.post:not(.upost):not(.featured)') : []).map(function (n) {
        var t = n.querySelector('time[datetime]'); return { node: n, t: t ? Date.parse(t.getAttribute('datetime') + 'T09:00:00+09:00') : 0 };
      });
    }
    function clear() { list.querySelectorAll(':scope > .upost, :scope > .feed-note, :scope > .feed-skel').forEach(function (n) { n.remove(); }); }
    function skeleton() { // 불러오는 동안 글 모양 자리(체감 속도)
      for (var i = 0; i < 2; i++) {
        var sk = el('div', 'card feed-skel'); sk.setAttribute('aria-hidden', 'true');
        sk.appendChild(el('span', 'sk-av')); var ln = el('span', 'sk-lines'); ln.appendChild(el('span', 'sk-l')); ln.appendChild(el('span', 'sk-l sk-l2')); sk.appendChild(ln);
        var first = list.firstElementChild; if (first) first.before(sk); else list.appendChild(sk);
      }
    }
    function nudge() { // 로그인 전: 피드 중간에 한 번, 바로 누를 수 있는 로그인 버튼(팝업이 아니라 글 사이 카드)
      var s = C.state(); if (s.me || s.logged || !s.providers.length) return;
      var kids = list.querySelectorAll(':scope > article.post'); var after = kids[4] || kids[kids.length - 1]; if (!after) return;
      var w = el('div', 'feed-note card nudge');
      w.appendChild(el('strong', 'nudge-t', '관심 종목 이야기를 놓치지 마세요'));
      w.appendChild(el('p', 'muted', '로그인하면 사람을 팔로우하고, 내 글에 답글이 달리면 알림을 받습니다. 이메일·전화번호는 받지 않습니다.'));
      var row = el('div', 'nudge-row');
      s.providers.forEach(function (pv) { var a = el('a', 'btn kw-login kw-login-' + pv, C.providerName(pv)); a.href = C.loginUrl(pv); row.appendChild(a); });
      w.appendChild(row); after.after(w);
    }
    function place(items, hot) {
      var R = reports(), gaps = R.map(function () { return []; }), tail = [], g = 0;
      items.forEach(function (c) {
        while (!hot && g < R.length && (c._t || c.created) < R[g].t) g++;   // (최신순일 때) 이 글보다 새 리포트는 건너뜀
        while (g < R.length && gaps[g].length >= 3) g++;  // 한 칸에 3개까지
        (g < R.length ? gaps[g] : tail).push(c);
      });
      R.forEach(function (r, i) { gaps[i].forEach(function (c) { r.node.before(render(c)); }); });
      appendTail(tail);
    }
    function appendTail(items) { items.forEach(function (c) { list.appendChild(render(c)); }); }
    // 팔로우한 사람이 리포스트한 리포트: 피드에 있는 그 리포트 카드를 복제해 '○○님이 리포스트함' 줄을 붙인다
    function render(c) {
      if (c.type !== 'report') return postCard(c);
      var orig = list.querySelector('article.post:not(.upost)[data-slug="' + c.slug + '"]'), card;
      if (orig) { card = orig.cloneNode(true); card.querySelectorAll('[data-post-top]').forEach(function (x) { x.remove(); }); }
      else {
        card = el('article', 'card post'); card.setAttribute('data-slug', c.slug);
        var a = el('a', 'post-body card-link'); a.href = C.reportUrl(c.slug); var h = el('h3', 'card-title', '리포트'); a.appendChild(h); card.appendChild(a);
        C.reportTitle(c.slug).then(function (r) { h.textContent = (r.k ? r.k + ' · ' : '') + C.shortTitle(r.t); });
      }
      card.classList.add('upost', 'rp-report');
      var line = el('a', 'rp-line'); line.href = C.profileUrl(c.rp.uid); line.textContent = '↻ ' + c.rp.nick + '님이 리포스트함';
      card.insertBefore(line, card.firstChild);
      return card;
    }
    function note(node) { var w = el('div', 'feed-note card'); w.appendChild(node); var first = list.firstElementChild; if (first) first.before(w); else list.appendChild(w); return w; }
    function emptyNote() {
      var s = C.state(), box = el('div');
      if (tab !== 'following') return;
      if (!s.me) {
        box.appendChild(el('p', null, '팔로우한 사람의 글이 여기에 모입니다. 로그인하고 관심 가는 사람을 팔로우해 보세요.'));
        var b = el('button', 'btn btn-primary', '로그인'); b.type = 'button'; b.addEventListener('click', function () { C.openAccount(); }); box.appendChild(b);
        note(box); return;
      }
      box.appendChild(el('p', null, '아직 팔로우한 사람·종목의 글이 없습니다. 관심 종목 페이지에서 "+ 팔로우"를 누르거나, 활발한 사람을 팔로우해 보세요.'));
      var w = note(box);
      (sgItems ? Promise.resolve(sgItems) : loadSuggest()).then(function (items) {
        if (!items.length) return; var ul = el('ul', 'sg-list'); suggestList(ul, items.slice(0, 3)); w.appendChild(ul);
      });
    }
    function load(reset) {
      if (loading) return Promise.resolve(); loading = true;
      var q = '/v1/feed?tab=' + tab + '&limit=' + (reset ? 30 : 20) + (tab === 'all' ? '&rank=hot' : '');
      if (!reset) q += hotMode ? '&offset=' + loaded : '&before=' + oldest;
      if (reset) { clear(); skeleton(); }
      // 팔로잉 탭: 팔로우한 종목·테마의 종토방 글도 함께
      var pre = tab === 'following' ? C.myTopics().then(function (items) { var b = C.topicBoards(items); boardsQ = b.length ? '&boards=' + b.join(',') : ''; return boardsQ; }) : Promise.resolve('');
      return pre.then(function (bq) { return api(q + bq); }).then(function (d) {
        loading = false;
        if (d._status !== 200) { clear(); return; }
        var items = d.items || [];
        if (reset) {
          clear(); hotMode = !!d.hot; loaded = 0; newBtn.hidden = true;
          newest = items.reduce(function (m, c) { return Math.max(m, c.created); }, 0) || Date.now();
          // 팔로잉 탭: 팔로우한 사람의 리포스트를 리포스트한 시각으로 섞는다(같은 글이 이미 있으면 한 번만)
          var have = {}; items.forEach(function (c) { have[c.id] = 1; });
          (d.reposts || []).forEach(function (x) { if (x.type === 'report' || !have[x.id]) { x._t = x.rp.at; items.push(x); if (x.id) have[x.id] = 1; } });
          if (d.reposts && d.reposts.length) items.sort(function (a, b) { return (b._t || b.created) - (a._t || a.created); });
          place(items, hotMode); if (!items.length) emptyNote(); nudge();
        } else appendTail(items);
        loaded += items.length;
        var ts = items.filter(function (c) { return c.created && !c.rp; }).map(function (c) { return c.created; });
        if (ts.length) oldest = Math.min.apply(null, ts);
        endEl.hidden = !d.more;
      }).catch(function () { loading = false; });
    }
    function setTab(t) {
      tab = t; try { localStorage.setItem('kw-tab', t); } catch (e) {}
      tabsEl.querySelectorAll('[data-tab]').forEach(function (b) { b.setAttribute('aria-selected', b.getAttribute('data-tab') === t ? 'true' : 'false'); });
      return load(true);
    }
    tabsEl.querySelectorAll('[data-tab]').forEach(function (b) {
      b.addEventListener('click', function () {
        var t = b.getAttribute('data-tab');
        if (t === tab && !feed.dirty) { feedEl.scrollIntoView({ behavior: 'smooth' }); return; }
        feed.dirty = false; setTab(t);
      });
    });
    moreBtn.addEventListener('click', function () { moreBtn.disabled = true; load(false).then(function () { moreBtn.disabled = false; }); });
    newBtn.addEventListener('click', function () { load(true).then(function () { feedEl.scrollIntoView({ behavior: 'smooth' }); }); });
    function poll() {
      if (pollN++ > 30) return;
      setTimeout(function () {
        if (document.hidden) { pollN--; poll(); return; }
        api('/v1/feed/new?tab=' + tab + '&since=' + newest + (tab === 'following' ? boardsQ : '')).then(function (d) {
          if (d.n > 0) { newBtn.textContent = '새 글 ' + (d.n >= 99 ? '99+' : d.n) + '개 보기'; newBtn.hidden = false; }
          poll();
        }).catch(function () {});
      }, 60000);
    }

    // 이번 주 가장 오래 읽힌 리포트를 피드 맨 위 '대표 글'로(실제로 본 시간 합계 기준, 매주 자동으로 바뀜)
    api('/v1/popular/read').then(function (d) {
      var top = (d.items || [])[0]; if (!top || list.querySelector('.featured')) return;
      var orig = list.querySelector('article.post:not(.upost)[data-slug="' + top.slug + '"]'), card;
      if (orig) { card = orig.cloneNode(true); card.querySelectorAll('[data-post-top]').forEach(function (x) { x.remove(); }); }
      else {
        card = el('article', 'card post'); card.setAttribute('data-slug', top.slug);
        var a = el('a', 'post-body card-link'); a.href = C.reportUrl(top.slug); var h = el('h3', 'card-title', '리포트'); a.appendChild(h); card.appendChild(a);
        C.reportTitle(top.slug).then(function (r) { h.textContent = (r.k ? r.k + ' · ' : '') + C.shortTitle(r.t); });
      }
      card.classList.add('featured');
      var m = Math.floor(top.avg / 60), sec = top.avg % 60;
      var badge = el('p', 'featured-badge', '★ 이번 주 가장 오래 읽힌 리포트 · 평균 ' + (m ? m + '분 ' : '') + sec + '초');
      card.insertBefore(badge, card.firstChild);
      card.addEventListener('click', function (e) { if (e.target.closest('a') && window.kwEv) kwEv('featured_click'); });
      var first = list.firstElementChild; if (first) first.before(card); else list.appendChild(card);
    }).catch(function () {});

    // 글쓰기 상자
    var cp = feedEl.querySelector('[data-composer]'), cf = cp.querySelector('form'), ta = cf.querySelector('textarea');
    var sel = cf.querySelector('[data-composer-board]'), lenEl = cf.querySelector('[data-composer-len]'), cmsg = cf.querySelector('[data-composer-msg]');
    var started = 0;
    var nickIn = cf.querySelector('[name=nick]');
    ta.addEventListener('focus', function () { if (window.kwEv) kwEv('compose_open'); });
    ta.addEventListener('input', function () {
      if (!started) started = Date.now();
      lenEl.textContent = ta.value.length + '/500';
      cp.classList.toggle('composer-on', ta.value.length > 0);
      // 글에 $티커를 쓰면 올릴 곳을 그 종목 종토방으로
      var m = /\$([A-Za-z]{1,6})(?![A-Za-z])/.exec(ta.value);
      if (m && sel.querySelector('option[value="b-' + m[1].toLowerCase() + '"]')) sel.value = 'b-' + m[1].toLowerCase();
    });
    cf.addEventListener('submit', function (e) {
      e.preventDefault();
      if (needNick()) return;
      var sb = cf.querySelector('[type=submit]'); sb.disabled = true; cmsg.textContent = '';
      var sentBody = ta.value;
      api('/v1/comments', { method: 'POST', body: { slug: sel.value, body: ta.value, nick: nickIn && !nickIn.hidden ? nickIn.value : '', website: cf.website.value, t: started ? Date.now() - started : 0 } }).then(function (d) {
        sb.disabled = false;
        if (d.error === 'account') { C.openAccount(); return; }
        if (!d.ok) { cmsg.textContent = d.message || '올리지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; return; }
        ta.value = ''; started = 0; lenEl.textContent = '0/500'; cp.classList.remove('composer-on');
        if (d.status === 'held') { cmsg.textContent = d.message; return; }
        toast('올렸습니다'); if (window.kwEv) kwEv('post_submit');
        // 방금 쓴 글은 순위와 상관없이 맨 위에 보여 준다
        var mine = { id: d.id, slug: sel.value, nick: d.nick || (C.state().me ? C.state().me.nick : '나'), uid: C.state().me ? C.state().me.id : null, body: sentBody, likes: 0, created: Date.now(), replies: 0, liked: false, mine: true };
        load(true).then(function () {
          var ex = list.querySelector('[data-pid="' + d.id + '"]'); if (ex) ex.remove();
          var first = list.firstElementChild, card = postCard(mine); card.classList.add('upost-new');
          if (first) first.before(card); else list.appendChild(card);
        });
      }).catch(function () { sb.disabled = false; cmsg.textContent = '올리지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; });
    });

    C.meReady.then(function () {
      var s = C.state();
      tabsEl.hidden = false; cp.hidden = false;
      var av = cp.querySelector('[data-composer-av]');
      if (s.me) { var a = C.avatar(s.me.nick, s.me.id); a.className += ' post-av'; av.appendChild(a); }
      else { // 로그인 전: 익명으로 바로 쓴다(닉네임은 선택)
        av.className += ' composer-av-guest';
        ta.placeholder = '종목 이야기를 나눠 보세요. 로그인 없이도 쓸 수 있어요.';
        cp.addEventListener('focusin', function () { nickIn.hidden = false; cp.classList.add('composer-on'); });
      }
      if (tab === 'following' && !s.me) tab = 'all';
      if (/[?&]compose=1/.test(location.search)) { // 아래 탭 줄의 '글쓰기'로 들어온 경우
        try { history.replaceState(null, '', location.pathname); } catch (e) {}
        cp.scrollIntoView({ block: 'center' }); ta.focus();
      }
      return setTab(tab);
    }).then(poll).catch(function () {});

    // 오른쪽 칸(휴대폰에서는 피드 중간): 팔로우 추천
    if (sgBox) loadSuggest().then(function (items) {
      if (!items.length) return;
      suggestList(sgBox.querySelector('[data-suggest-list]'), items);
      sgBox.hidden = false;
    });
  }

  // ---------- 글 상세(/p/?id=번호) ----------
  var pp = document.querySelector('[data-post-page]');
  if (pp) {
    var id = (/[?&]id=(\d+)/.exec(location.search) || [])[1];
    var msg = pp.querySelector('[data-pp-msg]'), holder = pp.querySelector('[data-pp-post]');
    var rbox = pp.querySelector('[data-pp-replies]'), rlist = pp.querySelector('[data-pp-list]'), rform = pp.querySelector('[data-pp-form]');
    var rta = rform.querySelector('textarea'), rlen = pp.querySelector('[data-pp-len]'), rmsg = pp.querySelector('[data-pp-fmsg]');
    var post = null, rstart = 0, adTpl = pp.querySelector('template[data-thread-ad]');
    function replyItem(c, liked) {
      var li = el('li', 'cm-item'); li.appendChild(C.avatar(c.nick, c.uid)); if (c.uid) { li.setAttribute('data-by-uid', c.uid); if (C.isBlocked(c.uid)) li.hidden = true; }
      var main = el('div', 'cm-main'), head = el('div', 'cm-head');
      head.appendChild(C.nickEl(c, 'cm-nick')); head.appendChild(el('span', 'cm-time muted', ago(c.created)));
      main.appendChild(head); main.appendChild(C.richText(el('p', 'cm-body'), c.body));
      var act = el('div', 'cm-act');
      var like = el('button', 'cm-like'); like.type = 'button';
      C.setHeart(like, c.likes, liked); like.disabled = !!c.mine;
      like.addEventListener('click', function () {
        like.disabled = true;
        api('/v1/comments/' + c.id + '/like', { method: 'POST' }).then(function (d) {
          like.disabled = false; if (d._status !== 200) { if (d.message) toast(d.message); return; }
          C.setHeart(like, d.likes, d.liked);
        }).catch(function () { like.disabled = false; });
      });
      act.appendChild(like);
      var x = el('button', 'cm-link', c.mine ? '삭제' : '신고'); x.type = 'button';
      x.addEventListener('click', function () {
        if (c.mine) { if (confirm('이 답글을 삭제할까요?')) api('/v1/comments/' + c.id + '/delete', { method: 'POST' }).then(loadPost); return; }
        if (!confirm('이 답글을 신고할까요? 신고가 쌓이면 자동으로 가려집니다.')) return;
        api('/v1/comments/' + c.id + '/report', { method: 'POST' }).then(function () { x.textContent = '신고됨'; x.disabled = true; });
      });
      act.appendChild(x); main.appendChild(act); li.appendChild(main);
      return li;
    }
    function placeAds() { // 답글 사이 광고(종토방과 같은 리듬)
      if (!adTpl) return;
      var first = +pp.getAttribute('data-ad-first') || 4, every = +pp.getAttribute('data-ad-every') || 6, max = +pp.getAttribute('data-ad-max') || 0;
      var items = Array.prototype.slice.call(rlist.children);
      for (var i = first, k = 0; i < items.length && k < max; i += every, k++) {
        var li = el('li', 'cm-ad'); li.appendChild(document.importNode(adTpl.content, true)); items[i - 1].after(li);
        if (window.kwAdNew) window.kwAdNew(li.querySelector('.ad-coupang-products'));
        if (li.querySelector('ins.adsbygoogle')) { try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {} }
      }
    }
    function loadPost() {
      return Promise.all([C.meReady, api('/v1/post/' + id)]).then(function (res) {
        var d = res[1];
        if (d._status !== 200) { msg.textContent = '찾을 수 없는 글입니다(삭제됐거나 가려진 글).'; return; }
        msg.hidden = true; post = d.post;
        var likedSet = {}; (d.liked || []).forEach(function (x) { likedSet[x] = 1; });
        holder.textContent = '';
        holder.appendChild(postCard({ id: post.id, slug: post.slug, nick: post.nick, uid: post.uid, body: post.body, likes: post.likes, created: post.created, replies: d.replies.length, liked: !!likedSet[post.id], mine: post.mine, quote: post.quote, reposts: post.reposts, reposted: post.reposted },
          { detail: true, onDelete: function () { location.href = base + '/'; } }));
        var tk = boardOf(post.slug), bl = pp.ownerDocument.querySelector('[data-pp-board]');
        if (bl) { bl.textContent = ''; if (tk) { var a = el('a', null, '· ' + tk + ' 종토방 전체 글'); a.href = base + '/t/' + tk.toLowerCase() + '/#board'; bl.appendChild(a); } else bl.appendChild(el('span', 'muted', '· 라운지')); }
        document.title = post.nick + ': ' + post.body.slice(0, 30) + ' | ' + document.title.split('|').pop().trim();
        rbox.hidden = false;
        pp.querySelector('[data-pp-count]').textContent = d.replies.length ? num(d.replies.length) : '';
        var s = C.state(), can = true;
        rform.hidden = false; pp.querySelector('[data-pp-need]').hidden = !!s.me || !s.providers.length;
        var rn = rform.querySelector('[name=nick]'); if (rn) rn.hidden = !!s.me;
        rlist.textContent = '';
        d.replies.forEach(function (c) { rlist.appendChild(replyItem(c, likedSet[c.id])); });
        if (!d.replies.length) rlist.appendChild(el('li', 'cm-empty muted', '첫 답글을 남겨 보세요.'));
        else placeAds();
        if (location.hash === '#reply') { rbox.scrollIntoView(); if (can) rta.focus({ preventScroll: true }); }
      }).catch(function () { msg.textContent = '글을 불러오지 못했습니다.'; });
    }
    rta.addEventListener('input', function () { if (!rstart) rstart = Date.now(); rlen.textContent = rta.value.length + '/500'; });
    rform.addEventListener('submit', function (e) {
      e.preventDefault(); if (!post) return;
      if (needNick()) return;
      var sb = rform.querySelector('[type=submit]'); sb.disabled = true; rmsg.textContent = '';
      api('/v1/comments', { method: 'POST', body: { slug: post.slug, body: rta.value, parent: post.id, nick: rform.nick && !rform.nick.hidden ? rform.nick.value : '', website: rform.website.value, t: rstart ? Date.now() - rstart : 0 } }).then(function (d) {
        sb.disabled = false;
        if (d.error === 'account') { C.openAccount(); return; }
        if (!d.ok) { rmsg.textContent = d.message || '등록하지 못했습니다.'; return; }
        rta.value = ''; rstart = 0; rlen.textContent = '0/500';
        if (d.status === 'held') { rmsg.textContent = d.message; return; }
        loadPost();
      }).catch(function () { sb.disabled = false; rmsg.textContent = '등록하지 못했습니다.'; });
    });
    if (!id) msg.textContent = '글 주소가 올바르지 않습니다.'; else loadPost();
  }
})();
