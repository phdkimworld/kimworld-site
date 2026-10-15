// 홈 피드(쓰레드·트위터식)와 글 상세(/p/?id=번호)
// · 홈: 하나의 커뮤니티 피드(추천·팔로잉을 섞은 순위). 김박사 월드 리포트(메인 포스트)가 사이사이 섞여 나온다.
// · 리포트·종목 화면: 그 리포트를 공유·인용한 글 / 그 종목 태그 글(댓글·종토방 대신)
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
    repost: 'm17 2.5 3 3-3 3M3.5 11V9.5a4 4 0 0 1 4-4H20M7 21.5l-3-3 3-3M20.5 13v1.5a4 4 0 0 1-4 4H4',
    eye: 'M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12zM12 14.8a2.8 2.8 0 1 0 0-5.6 2.8 2.8 0 0 0 0 5.6z'
  };
  // ---------- 조회수: 글 카드가 화면에 절반 이상 0.6초 보이면 한 번(같은 화면에서는 한 번만). 모아서 보낸다 ----------
  var vSeen = {}, vQueue = [], vTimer = 0, vObs = null;
  function vFlush() {
    clearTimeout(vTimer); vTimer = 0; if (!vQueue.length) return;
    var ids = vQueue.splice(0, 30);
    api('/v1/post-views', { method: 'POST', body: { ids: ids }, keepalive: true }).catch(function () {});
    if (vQueue.length) vTimer = setTimeout(vFlush, 1500);
  }
  if (window.IntersectionObserver) vObs = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      var n = e.target, id = n.getAttribute('data-pid');
      if (!id || vSeen[id]) return;
      if (e.isIntersecting) n._vt = setTimeout(function () {
        if (vSeen[id]) return; vSeen[id] = 1; vObs.unobserve(n); vQueue.push(id);
        if (!vTimer) vTimer = setTimeout(vFlush, 4000);
      }, 600);
      else clearTimeout(n._vt);
    });
  }, { threshold: 0.5 });
  addEventListener('pagehide', vFlush);
  document.addEventListener('visibilitychange', function () { if (document.hidden) vFlush(); });
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
    // 글은 API의 공유 미리보기 주소로(카카오톡·쓰레드에 글 내용이 보이게), 그 밖은 사이트 주소 + utm
    var m = /\/p\/\?id=(\d+)/.exec(url);
    var u = m && C.apiBase ? C.apiBase + '/s/p/' + m[1] : (window.kwShareUrl ? kwShareUrl(location.origin + url) : location.origin + url);
    if (window.kwEv) kwEv('share');
    if (navigator.share) { navigator.share({ title: title, url: u }).catch(function () {}); return; }
    (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(function () { toast('주소를 복사했습니다'); }, function () { prompt('주소를 복사하세요', u); });
  }

  // 화면에 없는 리포트의 피드 카드를 색인(search.json)으로 만든다(서버 카드 card()와 같은 모양: 머리·본문·차트·투표·반응 줄)
  function fullReportCard(slug, done) {
    var card = el('article', 'card post'); card.setAttribute('data-slug', slug);
    var a0 = el('a', 'post-body card-link'); a0.href = C.reportUrl(slug); var h0 = el('h3', 'card-title', '리포트'); a0.appendChild(h0); card.appendChild(a0);
    C.loadIndex().then(function (I) {
      var r = I.bySlug[slug]; if (!r) return;
      a0.remove(); card.setAttribute('data-ticker', r.k); // 앞에 붙은 표시(조회수 상위·리포스트 줄)는 그대로 둔다
      var head = el('header', 'post-head');
      var av = el('img', 'post-av'); av.src = base + '/static/icon.svg'; av.alt = ''; av.width = 38; av.height = 38; head.appendChild(av);
      var who = el('div', 'post-who'); who.appendChild(el('span', 'post-name', '김박사 월드'));
      who.appendChild(el('span', 'post-chev', '›')).setAttribute('aria-hidden', 'true');
      var g = el('a', 'post-group', r.c || r.k); g.href = base + '/t/' + String(r.k).toLowerCase() + '/'; who.appendChild(g);
      who.appendChild(el('span', 'post-time muted', '· ' + ago(new Date(r.d + 'T09:00:00+09:00').getTime())));
      head.appendChild(who); head.appendChild(followMini(r.k)); card.appendChild(head);
      var a = el('a', 'post-body card-link'); a.href = C.reportUrl(slug);
      a.appendChild(el('span', 'card-company', r.c || ''));
      a.appendChild(el('h3', 'card-title', r.st || r.t));
      a.appendChild(el('p', 'card-summary', r.s || ''));
      if (r.ch) { var m = el('span', 'post-media'), im = el('img'); im.src = r.ch; im.alt = (r.c || '') + ' 대표 가격 흐름'; im.loading = 'lazy'; m.appendChild(im); a.appendChild(m); }
      card.appendChild(a);
      // 투자 심리 투표(서버 카드와 같은 마크업)
      var fp = el('div', 'fpoll'); fp.setAttribute('data-fpoll', ''); fp.setAttribute('data-ticker', r.k); fp.hidden = true;
      fp.appendChild(el('span', 'fp-q', (r.c || r.k) + ', 앞으로?'));
      var fb = el('div', 'fp-btns');
      [['bull', '▲ 오를 것'], ['bear', '▼ 내릴 것']].forEach(function (x) { var b = el('button', 'fp-b fp-' + x[0], x[1]); b.type = 'button'; b.setAttribute('data-fp-v', x[0]); b.setAttribute('aria-pressed', 'false'); fb.appendChild(b); });
      fp.appendChild(fb);
      var tz = el('p', 'fp-tease', '🔒 투표하면 다른 투자자들의 결과가 보여요'); tz.setAttribute('data-fp-tease', ''); fp.appendChild(tz);
      var res = el('div', 'fp-res'); res.setAttribute('data-fp-res', ''); res.hidden = true;
      var bar = el('div', 'fp-bar'); var bb = el('i', 'fp-bb'); bb.setAttribute('data-fp-bb', ''); var br = el('i', 'fp-br'); br.setAttribute('data-fp-br', ''); bar.appendChild(bb); bar.appendChild(br); res.appendChild(bar);
      var ln = el('div', 'fp-line'); [['fp-up', 'data-fp-up'], ['fp-meta', 'data-fp-meta'], ['fp-down', 'data-fp-down']].forEach(function (x) { var sp = el('span', x[0]); sp.setAttribute(x[1], ''); ln.appendChild(sp); }); res.appendChild(ln);
      var mo = el('a', 'fp-more', '심리 추이 보기 →'); mo.href = base + '/t/' + String(r.k).toLowerCase() + '/#sent-h'; res.appendChild(mo);
      fp.appendChild(res); card.appendChild(fp);
      // 반응 줄
      var act = el('footer', 'post-actions');
      var lk = el('button', 'pa pa-like'); lk.type = 'button'; lk.setAttribute('data-post-like', ''); lk.setAttribute('aria-label', '좋아요'); lk.setAttribute('aria-pressed', 'false');
      lk.appendChild(icon('heart')); var lkn = el('span'); lkn.setAttribute('data-n', ''); lk.appendChild(lkn); act.appendChild(lk);
      var cm = el('a', 'pa'); cm.href = base + '/p/?r=' + slug; cm.setAttribute('aria-label', '답글·이야기 쓰레드'); cm.appendChild(icon('comment')); var cmn = el('span'); cm.appendChild(cmn); act.appendChild(cm);
      var rb = el('button', 'pa pa-repost'); rb.type = 'button'; rb.setAttribute('data-repost', ''); rb.setAttribute('data-kind', 'r'); rb.setAttribute('data-ref', slug); rb.setAttribute('data-quote-src', r.s || ''); rb.setAttribute('aria-pressed', 'false'); rb.setAttribute('aria-label', '리포스트·인용');
      rb.appendChild(icon('repost')); var rbn = el('span'); rbn.setAttribute('data-n', ''); rb.appendChild(rbn); act.appendChild(rb);
      var sh = el('button', 'pa pa-share'); sh.type = 'button'; sh.setAttribute('data-action', 'share'); sh.setAttribute('data-share-url', '/r/' + slug + '/'); sh.setAttribute('aria-label', '공유'); sh.appendChild(icon('share')); act.appendChild(sh);
      var vw = el('span', 'pa pa-static pa-views'); vw.hidden = true; vw.appendChild(icon('eye')); var vwn = el('span'); vw.appendChild(vwn); act.appendChild(vw);
      card.appendChild(act);
      api('/v1/stats?slugs=' + slug).then(function (d) {
        var x = ((d || {}).stats || {})[slug]; if (!x) return;
        lk.setAttribute('aria-pressed', x.liked ? 'true' : 'false'); lkn.textContent = x.likes ? num(x.likes) : '';
        cmn.textContent = x.comments ? num(x.comments) : '';
        rb.setAttribute('aria-pressed', x.reposted ? 'true' : 'false'); rbn.textContent = x.reposts ? num(x.reposts) : '';
        if (x.views) { vwn.textContent = num(x.views); vw.hidden = false; }
      }).catch(function () {});
      if (window.kwPolls) window.kwPolls(document);
      if (done) done(r);
    }).catch(function () {});
    return card;
  }
  // 피드 카드 머리의 작은 '팔로우'(종목). 칠하기는 community.js가 한꺼번에(KWC.topics)
  var topicT = 0;
  function followMini(tk) {
    var b = el('button', 'post-follow'); b.type = 'button'; b.hidden = true;
    b.setAttribute('data-topic', ''); b.setAttribute('data-topic-mini', ''); b.setAttribute('data-kind', 't'); b.setAttribute('data-key', tk);
    b.setAttribute('aria-pressed', 'false'); b.setAttribute('aria-label', tk + ' 팔로우');
    var l = el('span', null, '팔로우'); l.setAttribute('data-topic-label', ''); b.appendChild(l);
    clearTimeout(topicT); topicT = setTimeout(function () { if (C.topics) C.topics(document); if (window.kwPolls) window.kwPolls(document); }, 50);
    return b;
  }
  // ---------- 글 카드(피드·글 상세 공통) ----------
  function postCard(c, opt) {
    opt = opt || {};
    var art = el('article', 'card post upost' + (opt.detail ? ' upost-detail' : '') + (opt.anc ? ' upost-anc' : '') + (opt.reply ? ' upost-re' : ''));
    art.setAttribute('data-pid', c.id); art.setAttribute('data-board', c.slug || '');
    if (vObs && c.id) vObs.observe(art);
    if (c.rp) { // 팔로우한 사람이 리포스트한 글
      var rpl = el('a', 'rp-line'); rpl.href = C.profileUrl(c.rp.uid); rpl.textContent = '↻ ' + c.rp.nick + '님이 리포스트함'; art.appendChild(rpl);
    }
    var head = el('header', 'post-head');
    var av = C.avatar(c.nick, c.uid); av.className += ' post-av'; head.appendChild(av);
    if (c.uid) { art.setAttribute('data-by-uid', c.uid); if (C.isBlocked(c.uid)) art.hidden = true; }
    var who = el('div', 'post-who');
    who.appendChild(C.nickEl(c, 'post-name'));
    // 쓰레드처럼 '닉네임 › 종목': 종목 태그가 있으면 종목 이름(누르면 그 종목 커뮤니티), 없으면 이름만
    var tk = boardOf(c.slug), TKN = {}; ((window.KW || {}).tk || []).forEach(function (t) { TKN[t.c] = t.n; });
    if (tk && !opt.noGroup) {
      who.appendChild(el('span', 'post-chev', '›')).setAttribute('aria-hidden', 'true');
      var grp = el('a', 'post-group', TKN[tk] || '$' + tk);
      grp.href = base + '/t/' + tk.toLowerCase() + '/#community'; grp.title = tk + ' 커뮤니티';
      who.appendChild(grp);
    }
    if (c.pinned) who.appendChild(el('span', 'post-pin', '공지'));
    var tm = el(opt.detail ? 'span' : 'a', 'post-time muted', '· ' + ago(c.created));
    if (!opt.detail) tm.href = C.postUrl(c.id);
    tm.title = new Date(c.created).toLocaleString('ko-KR');
    who.appendChild(tm);
    head.appendChild(who);
    if (tk && !opt.noGroup && !opt.detail) head.appendChild(followMini(tk));
    art.appendChild(head);
    var body = C.richText(el('p', 'upost-body'), c.body);
    art.appendChild(body);
    // 리포트 쓰레드 안에서는 그 리포트를 문장 없이 공유한 상자는 감춘다(이미 맨 위가 그 리포트)
    if (c.quote && !(opt.inReport && c.quote.kind === 'r' && c.quote.ref === opt.inReport && !c.quote.text)) { var qb = C.quoteBox(c.quote); qb.classList.add('upost-quote'); art.appendChild(qb); }
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
    // 조회수(원글·답글 모두, 리포트 카드와 같은 눈 모양)
    if (c.views) { var vw = el('span', 'pa pa-static pa-views'); vw.setAttribute('aria-label', '조회 ' + c.views); vw.appendChild(icon('eye')); vw.appendChild(el('span', null, num(c.views))); act.appendChild(vw); }
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
      if (tk) { var bl = el('a', 'post-menu-i', tk + ' 커뮤니티 가기'); bl.href = base + '/t/' + tk.toLowerCase() + '/#community'; menu.appendChild(bl); }
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
    var newBtn = feedEl.querySelector('[data-feed-new]');
    var endEl = feedEl.querySelector('[data-feed-end]'), moreBtn = feedEl.querySelector('[data-feed-more]');
    // 탭 없이 하나의 피드: 서버가 반응 × 나와의 관계(팔로우한 사람·종목·테마, 최근 반응한 사람) × 신선도로 줄 세운다
    var tab = 'mix';
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
    // '글 더 보기'로 이어 불러온 글 사이에도 광고를 계속(8개마다). 애드핏은 운영정책상 이렇게 계속 불러올 수 없어 애드센스·쿠팡만(빌드가 검사)
    var moreAdT = document.querySelector('template[data-feed-more-ad]'), moreN = 0;
    function appendTail(items, more) {
      items.forEach(function (c) {
        list.appendChild(render(c));
        if (more && moreAdT && ++moreN % 8 === 0) {
          var w = el('div', 'feed-ad-more'); w.appendChild(document.importNode(moreAdT.content, true)); list.appendChild(w);
          if (window.kwAdNew) window.kwAdNew(w.querySelector('.ad-coupang-products'));
          if (w.querySelector('ins.adsbygoogle')) { try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {} }
        }
      });
    }
    // 팔로우한 사람이 리포스트한 리포트: 피드에 있는 그 리포트 카드를 복제해 '○○님이 리포스트함' 줄을 붙인다
    function render(c) {
      if (c.type !== 'report') return postCard(c);
      var orig = list.querySelector('article.post:not(.upost)[data-slug="' + c.slug + '"]'), card;
      var line = el('a', 'rp-line'); line.href = C.profileUrl(c.rp.uid); line.textContent = '↻ ' + c.rp.nick + '님이 리포스트함';
      if (orig) { card = orig.cloneNode(true); card.querySelectorAll('[data-post-top]').forEach(function (x) { x.remove(); }); }
      else card = fullReportCard(c.slug);
      card.classList.add('upost', 'rp-report');
      card.insertBefore(line, card.firstChild);
      return card;
    }
    function note(node) { var w = el('div', 'feed-note card'); w.appendChild(node); var first = list.firstElementChild; if (first) first.before(w); else list.appendChild(w); return w; }
    function load(reset) {
      if (loading) return Promise.resolve(); loading = true;
      var q = '/v1/feed?tab=mix&limit=' + (reset ? 30 : 20);
      if (!reset) q += hotMode ? '&offset=' + loaded : '&before=' + oldest;
      if (reset) { clear(); skeleton(); }
      // 팔로우한 종목·테마의 종토방 글은 점수를 더 받는다(로그인했을 때)
      var pre = C.state().me ? C.myTopics().then(function (items) { var b = C.topicBoards(items); boardsQ = b.length ? '&boards=' + b.join(',') : ''; boostReports(items); return boardsQ; }) : Promise.resolve('');
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
          place(items, hotMode); nudge();
        } else appendTail(items, true);
        loaded += items.length;
        var ts = items.filter(function (c) { return c.created && !c.rp; }).map(function (c) { return c.created; });
        if (ts.length) oldest = Math.min.apply(null, ts);
        endEl.hidden = !d.more;
      }).catch(function () { loading = false; });
    }
    // 팔로우한 종목·테마의 최신 리포트를 위로(최대 2개, 대표 글 다음). 리포트 순서는 그 밖에는 최신순 그대로
    var boosted = false;
    function boostReports(topics) {
      if (boosted || !topics || !topics.length) return; boosted = true;
      var T = {}; topics.forEach(function (x) { T[x.kind + ':' + x.key] = 1; });
      var R = reports(), first = R[0] && R[0].node; if (!first) return;
      var pick = R.slice(1).filter(function (r) {
        var tk = r.node.getAttribute('data-ticker'), thk = r.node.getAttribute('data-theme-slug');
        return (tk && T['t:' + tk.toUpperCase()]) || (thk && T['th:' + thk]);
      }).slice(0, 2);
      pick.reverse().forEach(function (r) { first.after(r.node); });
    }
    moreBtn.addEventListener('click', function () { moreBtn.disabled = true; load(false).then(function () { moreBtn.disabled = false; }); });
    newBtn.addEventListener('click', function () { load(true).then(function () { feedEl.scrollIntoView({ behavior: 'smooth' }); }); });
    function poll() {
      if (pollN++ > 30) return;
      setTimeout(function () {
        if (document.hidden) { pollN--; poll(); return; }
        api('/v1/feed/new?tab=all&since=' + newest).then(function (d) {
          if (d.n > 0) { newBtn.textContent = '새 글 ' + (d.n >= 99 ? '99+' : d.n) + '개 보기'; newBtn.hidden = false; }
          poll();
        }).catch(function () {});
      }, 60000);
    }

    // 최근 7일 조회수 1위 리포트를 피드 맨 위 '대표 글'로(운영자 결정 2026-10-14: 조회수 기준, 표시는 '조회수 상위'만)
    api('/v1/popular?days=7&limit=1').then(function (d) {
      var top = (d.items || [])[0]; if (!top || list.querySelector('.featured')) return;
      var orig = list.querySelector('article.post:not(.upost)[data-slug="' + top.slug + '"]'), card;
      if (orig) { card = orig.cloneNode(true); card.querySelectorAll('[data-post-top]').forEach(function (x) { x.remove(); }); }
      else card = fullReportCard(top.slug); // 첫 화면 카드에 없으면 색인으로 온전한 카드를
      card.classList.add('featured');
      var badge = el('p', 'featured-badge', '★ 조회수 상위');
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
      var n = ta.value.length; // 글자 수는 끝에 가까울 때만(남은 글자)
      lenEl.textContent = n > 400 ? String(500 - n) : ''; lenEl.classList.toggle('over', n > 480);
      if (n > 0) cp.classList.add('composer-on');
      ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 260) + 'px'; // 쓰는 만큼만 늘어난다
      // 글에 $티커를 쓰면 올릴 곳을 그 종목 종토방으로
      var m = /\$([A-Za-z]{1,6})(?![A-Za-z])/.exec(ta.value);
      if (m && sel.querySelector('option[value="b-' + m[1].toLowerCase() + '"]') && sel.value !== 'b-' + m[1].toLowerCase()) { sel.value = 'b-' + m[1].toLowerCase(); if (cp._paintTopic) cp._paintTopic(); }
      var sb0 = cf.querySelector('[type=submit]'); if (sb0) sb0.classList.toggle('is-empty', !ta.value.trim());
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
        ta.value = ''; started = 0; lenEl.textContent = ''; ta.style.height = ''; cp.classList.remove('composer-on'); if (cp._closeFull) cp._closeFull();
        sb.classList.add('is-empty');
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
      cp.hidden = false;
      var av = cp.querySelector('[data-composer-av]');
      // 쓰레드처럼: '이름 › + 종목 고르기' 줄 → 글 → 아래 [게시]. 휴대폰에서는 누르면 '새 글' 전체 화면
      var line = el('div', 'cp-line');
      line.appendChild(el('span', 'composer-name', s.me ? s.me.nick : '익명으로 쓰기'));
      line.appendChild(el('span', 'post-chev', '›')).setAttribute('aria-hidden', 'true');
      var topicBtn = el('button', 'cp-topic'); topicBtn.type = 'button';
      var topicX = el('button', 'cp-topic-x', '×'); topicX.type = 'button'; topicX.setAttribute('aria-label', '종목 태그 지우기');
      line.appendChild(topicBtn); line.appendChild(topicX);
      cp.querySelector('[data-composer-form]').insertBefore(line, ta);
      var chosen = false; // 직접 고르거나 $티커로 정해졌는지
      function paintTopic() {
        var o = sel.options[sel.selectedIndex], v = sel.value;
        topicBtn.textContent = '';
        if (!chosen || !o) { topicBtn.appendChild(document.createTextNode('+ 종목 태그')); topicBtn.classList.remove('on'); topicX.hidden = true; return; }
        topicBtn.classList.add('on'); topicX.hidden = false;
        topicBtn.appendChild(document.createTextNode(v === 'b-talk' ? '종목 태그 없음' : o.textContent.replace(/^\$\S+\s*/, '') || o.textContent));
        if (v !== 'b-talk') topicBtn.appendChild(el('span', 'cp-topic-code', ' ' + v.slice(2).toUpperCase()));
      }
      cp._paintTopic = function () { chosen = true; paintTopic(); };
      topicX.addEventListener('click', function () { sel.value = 'b-talk'; chosen = false; paintTopic(); ta.focus(); });
      topicBtn.addEventListener('click', function () { // 고르기 창: 검색 + 태그 없음 + 팔로우한 종목 먼저 + 전체 종목
        var body = C.dialog('종목 태그');
        var q = el('input', 'cp-pick-q'); q.type = 'search'; q.placeholder = '종목 이름이나 티커'; q.autocomplete = 'off'; body.appendChild(q);
        var ul = el('ul', 'kw-users cp-pick'); body.appendChild(ul);
        var opts = Array.prototype.slice.call(sel.options).map(function (o) { return { v: o.value, t: o.value === 'b-talk' ? '종목 태그 없이' : o.textContent.replace(/^\$\S+\s*/, ''), c: o.value === 'b-talk' ? '' : o.value.slice(2).toUpperCase() }; });
        C.myTopics().then(function (items) {
          var fav = {}; items.forEach(function (x) { if (x.kind === 't') fav['b-' + x.key.toLowerCase()] = 1; });
          opts.sort(function (a, b) { return (a.v === 'b-talk' ? -2 : fav[a.v] ? -1 : 0) - (b.v === 'b-talk' ? -2 : fav[b.v] ? -1 : 0); });
          function draw() {
            var k = q.value.trim().toLowerCase(); ul.textContent = '';
            opts.filter(function (o) { return !k || o.t.toLowerCase().indexOf(k) >= 0 || o.c.toLowerCase().indexOf(k.replace(/^\$/, '')) === 0; }).slice(0, 60).forEach(function (o) {
              var li = el('li', 'kw-user kw-user-pick'); li.tabIndex = 0;
              var ic = el('span', 'cp-pick-ic' + (o.v === 'b-talk' ? ' talk' : ''), o.v === 'b-talk' ? '💬' : o.c.slice(0, 4)); li.appendChild(ic);
              var w = el('div', 'kw-user-who'); w.appendChild(el('strong', null, o.t));
              w.appendChild(el('span', 'muted kw-small', o.v === 'b-talk' ? '커뮤니티 전체에만 올리기' : '$' + o.c + (fav[o.v] ? ' · 팔로우 중' : ''))); li.appendChild(w);
              if (o.v === sel.value && chosen) li.appendChild(el('span', 'cp-pick-on', '✓'));
              var go = function () { sel.value = o.v; chosen = true; paintTopic(); var d = document.querySelector('dialog.kw-dlg[open]'); if (d) d.close(); setTimeout(function () { ta.focus(); }, 30); };
              li.addEventListener('click', go); li.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
              ul.appendChild(li);
            });
          }
          q.addEventListener('input', draw); draw();
          setTimeout(function () { q.focus(); }, 60);
        });
      });
      paintTopic();
      // 휴대폰: 누르면 '새 글' 전체 화면(× 로 닫으면 쓰던 글은 그대로 남는다)
      var top = el('div', 'cp-top');
      var cx = el('button', 'cp-close', '×'); cx.type = 'button'; cx.setAttribute('aria-label', '닫기');
      top.appendChild(cx); top.appendChild(el('strong', null, '새 글'));
      cp.insertBefore(top, cp.firstChild);
      var mq = window.matchMedia ? matchMedia('(max-width: 759px)') : null;
      // 휴대폰 뒤로가기: '새 글' 화면을 열 때 기록을 하나 쌓아 두고, 뒤로가기를 누르면 사이트를 떠나지 않고 이 화면만 닫아 메인 피드로
      var pushed = false;
      function openFull() {
        if (!mq || !mq.matches || cp.classList.contains('cp-full')) return;
        cp.classList.add('cp-full', 'composer-on'); document.documentElement.classList.add('cp-open');
        if (window.history && history.pushState) { try { history.pushState({ kwCompose: 1 }, ''); pushed = true; } catch (e) {} }
      }
      function shut() { cp.classList.remove('cp-full'); document.documentElement.classList.remove('cp-open'); ta.blur(); if (!ta.value.trim()) cp.classList.remove('composer-on'); }
      function closeFull() { if (pushed) { pushed = false; history.back(); return; } shut(); } // 기록을 되돌리면 popstate에서 닫힌다
      addEventListener('popstate', function () { if (cp.classList.contains('cp-full')) { pushed = false; shut(); var d = document.querySelector('dialog.kw-dlg[open]'); if (d) d.close(); window.scrollTo(0, 0); } });
      cx.addEventListener('click', closeFull);
      ta.addEventListener('focus', openFull);
      cp._closeFull = closeFull;
      ta.placeholder = '새로운 소식이 있나요?'; ta.rows = 1;
      if (s.me) { var a = C.avatar(s.me.nick, s.me.id); a.className += ' post-av'; av.appendChild(a); }
      else { // 로그인 전: 익명으로 바로 쓴다(닉네임은 선택)
        av.className += ' composer-av-guest';
        cp.addEventListener('focusin', function () { nickIn.hidden = false; });
      }
      cp.addEventListener('focusin', function () { cp.classList.add('composer-on'); if (!ta.value) ta.placeholder = '$티커를 쓰면 그 종목 태그가 붙어요'; });
      cp.addEventListener('focusout', function () {
        setTimeout(function () { if (!cp.classList.contains('cp-full') && !cp.contains(document.activeElement) && !document.querySelector('dialog.kw-dlg[open]') && !ta.value.trim()) { cp.classList.remove('composer-on'); ta.placeholder = '새로운 소식이 있나요?'; } }, 150);
      });
      if (/[?&]compose=1/.test(location.search)) { // 아래 탭 줄의 '글쓰기'로 들어온 경우
        try { history.replaceState(null, '', location.pathname); } catch (e) {}
        cp.scrollIntoView({ block: 'center' }); ta.focus();
      }
      return load(true);
    }).then(poll).catch(function () {});

    // 오른쪽 칸(휴대폰에서는 피드 중간): 팔로우 추천
    if (sgBox) loadSuggest().then(function (items) {
      if (!items.length) return;
      suggestList(sgBox.querySelector('[data-suggest-list]'), items);
      sgBox.hidden = false;
    });
  }

  // ---------- 리포트·종목 화면의 커뮤니티 ----------
  // 댓글·종토방을 따로 두지 않는다. 리포트 아래에는 '이 리포트를 공유·인용한 커뮤니티 글'(+ 같은 종목 최근 글),
  // 종목 화면에는 그 종목 태그가 붙은 커뮤니티 글. 글쓰기는 리포트를 첨부하거나 종목 태그를 붙여 커뮤니티에 올린다.
  var cm = document.querySelector('[data-community]');
  if (cm) {
    var about = cm.getAttribute('data-about') || '', cboard = cm.getAttribute('data-board') || '', ctk = boardOf(cboard);
    var cl = cm.querySelector('[data-cmty-list]'), cmore = cm.querySelector('[data-cmty-more]'), cn = cm.querySelector('[data-cmty-n]');
    var cadT = cm.querySelector('template[data-thread-ad]');
    var adFirst = +cm.getAttribute('data-ad-first') || 4, adEvery = +cm.getAttribute('data-ad-every') || 6, adMax = +cm.getAttribute('data-ad-max') || 0;
    var cOld = 0, shown = {}, nPosts = 0, nAds = 0, cLoading = false;
    var CTKN = {}; ((window.KW || {}).tk || []).forEach(function (t) { CTKN[t.c] = t.n; });
    function cAd() { // 글 사이 광고(같은 리듬: 4개 뒤부터 6개마다)
      if (!cadT || nAds >= adMax || nPosts < adFirst || (nPosts - adFirst) % adEvery) return;
      var w = el('div', 'cmty-ad'); w.appendChild(document.importNode(cadT.content, true)); cl.appendChild(w); nAds++;
      if (window.kwAdNew) window.kwAdNew(w.querySelector('.ad-coupang-products'));
      if (w.querySelector('ins.adsbygoogle')) { try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {} }
    }
    function cAdd(items) {
      items.forEach(function (c) {
        if (shown[c.id]) return; shown[c.id] = 1;
        cl.appendChild(postCard(c, { noGroup: !!ctk && c.slug === cboard })); nPosts++; cAd();
      });
    }
    function cEmpty(t) { var p = el('p', 'cmty-empty muted', t); cl.appendChild(p); }
    function cLoad(reset) {
      if (cLoading) return Promise.resolve(); cLoading = true;
      if (reset) { cOld = 0; shown = {}; nPosts = 0; nAds = 0; }
      var reqs = about
        ? [api('/v1/feed?about=' + about + '&limit=30'), cboard ? api('/v1/feed?board=' + cboard + '&limit=8') : Promise.resolve({})]
        : [api('/v1/feed?board=' + cboard + '&limit=20' + (reset ? '' : '&before=' + cOld))];
      return Promise.all(reqs).then(function (res) {
        cLoading = false;
        var d = res[0] || {}, items = d.items || [];
        if (reset) cl.textContent = '';
        if (about) {
          cn.textContent = items.length ? num(items.length) + (d.more ? '+' : '') : '';
          document.querySelectorAll('[data-report-bar] [data-post-cm]').forEach(function (x) { x.textContent = items.length ? num(items.length) + (d.more ? '+' : '') : ''; });
          if (!items.length) cEmpty('아직 이 리포트 이야기가 없어요. 첫 글을 남겨 보세요.');
          cAdd(items);
          var more = ((res[1] || {}).items || []).filter(function (x) { return !(x.quote && x.quote.ref === about); }).slice(0, 5);
          if (more.length) { cl.appendChild(el('h3', 'cmty-sub', (CTKN[ctk] || ctk) + ' 커뮤니티 최근 글')); cAdd(more); }
        } else {
          if (reset) cAdd(d.pinned || []);
          if (reset && !items.length) cEmpty('아직 글이 없어요. 이 종목에 대한 첫 글을 남겨 보세요.');
          cAdd(items);
          var ts = items.map(function (c) { return c.created; }); if (ts.length) cOld = Math.min.apply(null, ts);
          if (cmore) cmore.hidden = !d.more;
          if (reset) document.querySelectorAll('[data-cmty-n-tab]').forEach(function (x) { x.textContent = items.length ? num(items.length) + (d.more ? '+' : '') : ''; });
        }
        cm.hidden = false;
      }).catch(function () { cLoading = false; });
    }
    if (cmore) cmore.addEventListener('click', function () { cmore.disabled = true; cLoad(false).then(function () { cmore.disabled = false; }); });
    var cbtn = cm.querySelector('[data-cmty-compose]');
    window.kwCmtyDone = function () { cLoad(true).then(function () { cm.scrollIntoView({ behavior: 'smooth', block: 'start' }); }); };
    cbtn.addEventListener('click', function () { C.openCompose(about ? { kind: 'r', ref: about, text: '' } : null, { board: cboard }); });
    C.meReady.then(function () {
      var s = C.state(), avb = cm.querySelector('[data-cmty-av]');
      if (avb) { avb.textContent = ''; avb.appendChild(s.me ? C.avatar(s.me.nick, s.me.id) : C.avatar('익')); }
    });
    // 예전 주소(#comments·#board)로 들어와도 커뮤니티로
    var cHere = /^#(community|comments|board)$/.test(location.hash);
    var cGo = function () { cLoad(true).then(function () { if (cHere) cm.scrollIntoView(); }); };
    if (cHere || !about) cGo(); else setTimeout(cGo, 300); // 리포트는 본문을 먼저 그린 뒤
  }

  // ---------- 글 상세(/p/?id=번호) · 리포트 쓰레드(/p/?r=리포트) ----------
  // 쓰레드처럼: 위로 이어진 글(맥락) → 이 글 → 답글 쓰기 → 바로 아래 답글들(답글도 원글과 같은 카드: 좋아요·답글·리포스트·공유·조회수).
  // 리포트 쓰레드: 맨 위가 리포트 카드(본문을 누르면 리포트 화면), 답글 = 그 리포트를 공유·인용한 커뮤니티 글. 답글을 쓰면 리포트를 붙인 커뮤니티 글이 된다.
  var pp = document.querySelector('[data-post-page]');
  if (pp) {
    var id = (/[?&]id=(\d+)/.exec(location.search) || [])[1];
    var rslug = (/[?&]r=([a-z0-9-]+)/.exec(location.search) || [])[1];
    var msg = pp.querySelector('[data-pp-msg]'), holder = pp.querySelector('[data-pp-post]'), ancEl = pp.querySelector('[data-pp-anc]');
    var rbox = pp.querySelector('[data-pp-replies]'), rlist = pp.querySelector('[data-pp-list]'), rform = pp.querySelector('[data-pp-form]');
    var rta = rform.querySelector('textarea'), rlen = pp.querySelector('[data-pp-len]'), rmsg = pp.querySelector('[data-pp-fmsg]');
    var post = null, rep = null, rstart = 0, adTpl = pp.querySelector('template[data-thread-ad]');
    var back = document.querySelector('[data-pp-back]');
    if (back) back.addEventListener('click', function (e) { // 피드에서 왔으면 피드의 그 자리로 돌아간다
      if (document.referrer && document.referrer.indexOf(location.origin) === 0 && history.length > 1) { e.preventDefault(); history.back(); }
    });
    function placeAds() { // 답글 사이 광고(커뮤니티 목록과 같은 리듬)
      if (!adTpl) return;
      var first = +pp.getAttribute('data-ad-first') || 4, every = +pp.getAttribute('data-ad-every') || 6, max = +pp.getAttribute('data-ad-max') || 0;
      var items = Array.prototype.slice.call(rlist.children);
      for (var i = first, k = 0; i < items.length && k < max; i += every, k++) {
        var w = el('div', 'cmty-ad'); w.appendChild(document.importNode(adTpl.content, true)); items[i - 1].after(w);
        if (window.kwAdNew) window.kwAdNew(w.querySelector('.ad-coupang-products'));
        if (w.querySelector('ins.adsbygoogle')) { try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {} }
      }
    }
    function showReplies(list, count, opt) {
      rbox.hidden = false;
      pp.querySelector('[data-pp-count]').textContent = count ? num(count) : '';
      var s = C.state();
      rform.hidden = false;
      var avb = pp.querySelector('[data-pp-av]'); avb.textContent = ''; avb.appendChild(s.me ? C.avatar(s.me.nick, s.me.id) : C.avatar('익'));
      var rn = rform.querySelector('[name=nick]'); if (rn) rn.hidden = !!s.me;
      rlist.textContent = '';
      list.forEach(function (c) { rlist.appendChild(postCard(c, { reply: opt.reply, inReport: opt.inReport, noGroup: !!opt.inReport || c.slug === opt.sameBoard })); });
      if (!list.length) rlist.appendChild(el('p', 'cm-empty muted', opt && opt.inReport ? '아직 이 리포트 이야기가 없어요. 첫 글을 남겨 보세요.' : '첫 답글을 남겨 보세요.'));
      else placeAds();
      if (location.hash === '#reply') { rbox.scrollIntoView(); rta.focus({ preventScroll: true }); }
    }
    function loadPost() {
      return Promise.all([C.meReady, api('/v1/post/' + id)]).then(function (res) {
        var d = res[1];
        if (d._status !== 200) { msg.textContent = '찾을 수 없는 글입니다(삭제됐거나 가려진 글).'; return; }
        msg.hidden = true; post = d.post;
        ancEl.textContent = '';
        (d.ancestors || []).forEach(function (a) {
          if (a.gone) { ancEl.appendChild(el('p', 'upost-gone muted', '삭제되었거나 가려진 글입니다.')); return; }
          ancEl.appendChild(postCard(a, { anc: true, noGroup: a.slug === post.slug }));
        });
        holder.textContent = '';
        holder.appendChild(postCard(post, { detail: true, onDelete: function () { location.href = post.parent ? C.postUrl(post.parent) : base + '/'; } }));
        var tk = boardOf(post.slug), bl = document.querySelector('[data-pp-board]');
        if (bl) { bl.textContent = ''; if (tk) { var a = el('a', null, '· ' + tk + ' 커뮤니티'); a.href = base + '/t/' + tk.toLowerCase() + '/#community'; bl.appendChild(a); } }
        document.title = post.nick + ': ' + post.body.slice(0, 30) + ' | ' + document.title.split('|').pop().trim();
        rta.placeholder = post.nick + '님에게 답글 남기기';
        showReplies(d.replies, post.replies, { reply: true, sameBoard: post.slug });
        if (ancEl.lastElementChild && !location.hash) holder.scrollIntoView({ block: 'start' }); // 답글을 열면 그 글이 화면 위에, 위 글은 스크롤해서
      }).catch(function () { msg.textContent = '글을 불러오지 못했습니다.'; });
    }
    // 리포트 카드(쓰레드 맨 위): 본문을 누르면 리포트 화면, 아래 반응 줄은 피드 리포트 카드와 같다
    function reportCard(r, st) {
      var art = el('article', 'card post upost upost-detail pp-report'); art.setAttribute('data-slug', rep);
      var head = el('header', 'post-head');
      var av = el('img', 'post-av'); av.src = base + '/static/icon.svg'; av.alt = ''; av.width = 38; av.height = 38; head.appendChild(av);
      var who = el('div', 'post-who'); who.appendChild(el('span', 'post-name', '김박사 월드'));
      who.appendChild(el('span', 'post-chev', '›')).setAttribute('aria-hidden', 'true');
      var g = el('a', 'post-group', r.c || r.k); g.href = base + '/t/' + String(r.k).toLowerCase() + '/'; who.appendChild(g);
      who.appendChild(el('span', 'post-time muted', '· ' + String(r.d || '').replace(/-/g, '.')));
      head.appendChild(who); head.appendChild(followMini(String(r.k).toUpperCase())); art.appendChild(head);
      var a = el('a', 'post-body card-link'); a.href = C.reportUrl(rep);
      a.appendChild(el('h1', 'card-title pp-report-title', r.st || r.t));
      a.appendChild(el('p', 'card-summary', r.s || ''));
      if (r.ch) { var m = el('span', 'post-media'), im = el('img'); im.src = r.ch; im.alt = (r.c || '') + ' 대표 가격 흐름'; im.loading = 'lazy'; m.appendChild(im); a.appendChild(m); }
      a.appendChild(el('span', 'pp-report-go', '리포트 전체 읽기 →'));
      art.appendChild(a);
      var act = el('footer', 'post-actions');
      var lk = el('button', 'pa pa-like'); lk.type = 'button'; lk.setAttribute('data-post-like', ''); lk.setAttribute('aria-label', '좋아요');
      lk.setAttribute('aria-pressed', st.liked ? 'true' : 'false'); lk.appendChild(icon('heart')); var ln = el('span', null, st.likes ? num(st.likes) : ''); ln.setAttribute('data-n', ''); lk.appendChild(ln);
      act.appendChild(lk);
      var rp = el('a', 'pa'); rp.href = '#reply'; rp.setAttribute('aria-label', '답글'); rp.appendChild(icon('comment')); rp.appendChild(el('span', null, st.comments ? num(st.comments) : '')); act.appendChild(rp);
      var rb = el('button', 'pa pa-repost'); rb.type = 'button'; rb.setAttribute('aria-label', '리포스트·인용');
      rb.setAttribute('data-repost', ''); rb.setAttribute('data-kind', 'r'); rb.setAttribute('data-ref', rep); rb.setAttribute('data-quote-src', r.s || '');
      rb.setAttribute('aria-pressed', st.reposted ? 'true' : 'false'); rb.appendChild(icon('repost')); var rn = el('span', null, st.reposts ? num(st.reposts) : ''); rn.setAttribute('data-n', ''); rb.appendChild(rn); act.appendChild(rb);
      var sh = el('button', 'pa pa-share'); sh.type = 'button'; sh.setAttribute('aria-label', '공유'); sh.appendChild(icon('share'));
      sh.addEventListener('click', function () { share(C.reportUrl(rep).replace(location.origin, ''), r.st || r.t); }); act.appendChild(sh);
      if (st.views) { var vw = el('span', 'pa pa-static pa-views'); vw.appendChild(icon('eye')); vw.appendChild(el('span', null, num(st.views))); act.appendChild(vw); }
      art.appendChild(act);
      return art;
    }
    function loadReport() {
      return Promise.all([C.meReady, C.loadIndex(), api('/v1/stats?slugs=' + rep), api('/v1/feed?about=' + rep + '&limit=30')]).then(function (res) {
        var r = res[1].bySlug[rep];
        if (!r) { msg.textContent = '찾을 수 없는 리포트입니다.'; return; }
        msg.hidden = true;
        var st = ((res[2] || {}).stats || {})[rep] || {}, d = res[3] || {};
        holder.textContent = ''; holder.appendChild(reportCard(r, st));
        var bl = document.querySelector('[data-pp-board]');
        if (bl) { bl.textContent = ''; var a = el('a', null, '· ' + r.k + ' 커뮤니티'); a.href = base + '/t/' + String(r.k).toLowerCase() + '/#community'; bl.appendChild(a); }
        document.title = (r.st || r.t) + ' · 이야기 | ' + document.title.split('|').pop().trim();
        post = { report: r };
        rta.placeholder = '이 리포트에 대한 생각을 남겨 보세요';
        showReplies(d.items || [], (d.items || []).length, { inReport: rep });
      }).catch(function () { msg.textContent = '불러오지 못했습니다.'; });
    }
    rta.addEventListener('input', function () {
      if (!rstart) rstart = Date.now(); var n = rta.value.length; rlen.textContent = n > 400 ? String(500 - n) : '';
      rta.style.height = 'auto'; rta.style.height = Math.min(rta.scrollHeight, 220) + 'px';
    });
    rform.addEventListener('submit', function (e) {
      e.preventDefault(); if (!post) return;
      if (needNick()) return;
      var sb = rform.querySelector('[type=submit]'); sb.disabled = true; rmsg.textContent = '';
      var body = { body: rta.value, nick: rform.nick && !rform.nick.hidden ? rform.nick.value : '', website: rform.website.value, t: rstart ? Date.now() - rstart : 0 };
      if (post.report) { body.slug = 'b-' + String(post.report.k).toLowerCase(); body.quote = { kind: 'r', ref: rep, text: '' }; } // 리포트에 다는 답글 = 리포트를 붙인 커뮤니티 글
      else { body.slug = post.slug; body.parent = post.id; }
      api('/v1/comments', { method: 'POST', body: body }).then(function (d) {
        sb.disabled = false;
        if (d.error === 'account') { C.openAccount(); return; }
        if (!d.ok) { rmsg.textContent = d.message || '등록하지 못했습니다.'; return; }
        rta.value = ''; rstart = 0; rlen.textContent = ''; rta.style.height = '';
        if (d.status === 'held') { rmsg.textContent = d.message; return; }
        if (window.kwEv) kwEv(post.report ? 'quote_submit' : 'post_submit');
        (post.report ? loadReport() : loadPost());
      }).catch(function () { sb.disabled = false; rmsg.textContent = '등록하지 못했습니다.'; });
    });
    if (rslug) { rep = rslug; window.kwCmtyDone = function () { loadReport(); }; loadReport(); }
    else if (!id) msg.textContent = '글 주소가 올바르지 않습니다.'; else loadPost();
  }
})();
