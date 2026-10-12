// 조회수·댓글·좋아요·많이 본 리포트·요즘 찾는 종목 (api.drkimworld.com)
// API가 꺼져 있거나 응답이 없으면 해당 영역을 숨긴 채로 둔다(사이트는 그대로 동작).
(function () {
  var KW = window.KW || {};
  var API = (KW.api || '').replace(/\/+$/, '');
  var base = KW.base || '';
  if (!API) return;

  function api(path, opt) {
    opt = opt || {};
    var ctl = window.AbortController ? new AbortController() : null;
    var t = ctl ? setTimeout(function () { ctl.abort(); }, 6000) : 0;
    return fetch(API + path, {
      method: opt.method || 'GET',
      headers: opt.body ? { 'Content-Type': 'application/json' } : undefined,
      body: opt.body ? JSON.stringify(opt.body) : undefined,
      keepalive: !!opt.keepalive,
      signal: ctl ? ctl.signal : undefined
    }).then(function (r) {
      clearTimeout(t);
      return r.json().then(function (d) { d = d || {}; d._status = r.status; return d; });
    });
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function num(n) { return Number(n || 0).toLocaleString('ko-KR'); }
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

  // ---------- 리포트: 댓글 ----------
  var box = document.querySelector('[data-comments]');
  if (box && slug) {
    var listEl = box.querySelector('[data-cm-list]');
    var bestEl = box.querySelector('[data-cm-best]');
    var countEl = box.querySelector('[data-cm-count]');
    var form = box.querySelector('[data-cm-form]');
    var msg = box.querySelector('[data-cm-msg]');
    var lenEl = box.querySelector('[data-cm-len]');
    var sort = 'top';
    var startedAt = 0;
    var liked = {};

    function item(c, isBest) {
      var li = el('li', 'cm-item' + (isBest ? ' cm-item-best' : ''));
      var head = el('div', 'cm-head');
      if (isBest) head.appendChild(el('span', 'cm-badge', 'BEST'));
      head.appendChild(el('strong', 'cm-nick', c.nick));
      head.appendChild(el('span', 'cm-time muted', ago(c.created)));
      li.appendChild(head);
      li.appendChild(el('p', 'cm-body', c.body));
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
      if (c.mine) {
        var del = el('button', 'cm-link', '삭제'); del.type = 'button';
        del.addEventListener('click', function () {
          if (!confirm('이 댓글을 삭제할까요?')) return;
          api('/v1/comments/' + c.id + '/delete', { method: 'POST' }).then(load).catch(function () {});
        });
        act.appendChild(del);
      } else {
        var rep = el('button', 'cm-link', '신고'); rep.type = 'button';
        rep.addEventListener('click', function () {
          if (!confirm('이 댓글을 신고할까요? 신고가 쌓이면 자동으로 가려집니다.')) return;
          api('/v1/comments/' + c.id + '/report', { method: 'POST' }).then(function () { rep.textContent = '신고됨'; rep.disabled = true; }).catch(function () {});
        });
        act.appendChild(rep);
      }
      li.appendChild(act);
      return li;
    }

    function load() {
      return api('/v1/comments?slug=' + encodeURIComponent(slug) + '&sort=' + sort).then(function (d) {
        if (d._status !== 200) return;
        box.hidden = false;
        var jump = document.querySelector('[data-cm-jump]');
        if (jump) { jump.hidden = false; jump.textContent = '댓글 ' + (d.comments.length ? num(d.comments.length) : ''); }
        liked = {}; (d.liked || []).forEach(function (id) { liked[id] = true; });
        countEl.textContent = d.comments.length ? num(d.comments.length) : '';
        var nickInput = form.querySelector('[name=nick]');
        if (nickInput && !nickInput.value) nickInput.placeholder = '닉네임 (비우면 ' + d.me + ')';
        var bol = bestEl.querySelector('ol'); bol.textContent = '';
        (d.best || []).forEach(function (c) { bol.appendChild(item(c, true)); });
        bestEl.hidden = !(d.best && d.best.length);
        listEl.textContent = '';
        if (!d.comments.length) listEl.appendChild(el('li', 'cm-empty muted', '첫 댓글을 남겨 주세요.'));
        d.comments.forEach(function (c) { listEl.appendChild(item(c, false)); });
        if (sort === 'top') renderTop(d);
      });
    }

    // 요약 바로 아래 '인기 댓글': 베스트(좋아요 3개 이상) → 좋아요 받은 댓글 많은 순 2개 → 없으면 최근 댓글 1개
    var topEl = document.querySelector('[data-cm-top]');
    function renderTop(d) {
      if (!topEl) return;
      var seen = {};
      var picks = (d.best || []).concat(d.comments.filter(function (c) { return c.likes > 0; }))
        .filter(function (c) { if (seen[c.id]) return false; seen[c.id] = 1; return true; }).slice(0, 2);
      var hot = picks.length > 0;
      if (!hot) picks = d.comments.slice(0, 1); // 아직 좋아요가 없으면 가장 최근 댓글 하나
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
      var btn = form.querySelector('[type=submit]'); btn.disabled = true; msg.textContent = '';
      api('/v1/comments', { method: 'POST', body: {
        slug: slug, nick: form.nick.value, body: ta.value, website: form.website.value,
        t: startedAt ? Date.now() - startedAt : 0
      } }).then(function (d) {
        btn.disabled = false;
        if (!d.ok) { msg.textContent = d.message || '등록하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; return; }
        ta.value = ''; lenEl.textContent = '0/500'; startedAt = 0;
        msg.textContent = d.status === 'held' ? d.message : '등록했습니다.';
        sort = 'new';
        box.querySelectorAll('[data-sort]').forEach(function (x) { x.setAttribute('aria-selected', x.getAttribute('data-sort') === 'new' ? 'true' : 'false'); });
        load().catch(function () {});
      }).catch(function () { btn.disabled = false; msg.textContent = '등록하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'; });
    });

    // 첫 화면을 다 그린 뒤 불러온다(본문 표시를 늦추지 않게). #comments 로 들어오면 바로
    var go = function () { load().then(function () { if (location.hash === '#comments') box.scrollIntoView(); }).catch(function () {}); };
    if (location.hash === '#comments') go(); else setTimeout(go, 300);
  }

  // ---------- 검색어 기록(검색 페이지) ----------
  var lastLogged = '', logTimer = 0;
  window.kwLogSearch = function (q, hits) {
    clearTimeout(logTimer);
    q = String(q || '').trim();
    if (q.length < 2 || !hits || q === lastLogged) return;
    logTimer = setTimeout(function () { lastLogged = q; api('/v1/search', { method: 'POST', body: { q: q }, keepalive: true }).catch(function () {}); }, 1500);
  };

  // ---------- 홈: 많이 본 리포트 / 요즘 많이 찾는 종목 ----------
  var ins = document.querySelector('[data-insights]');
  if (ins) {
    var norm = function (s) { return String(s || '').toLowerCase().replace(/[\s·\-_.,()]/g, ''); };
    Promise.all([
      fetch(base + '/search.json').then(function (r) { return r.json(); }),
      api('/v1/popular?days=7&limit=5').catch(function () { return {}; }),
      api('/v1/trending?days=7').catch(function () { return {}; })
    ]).then(function (res) {
      var idx = res[0] || [], pop = res[1] || {}, tr = res[2] || {};
      var bySlug = {};
      idx.forEach(function (r) { var m = String(r.u).match(/\/r\/([^/]+)\/?$/); if (m) bySlug[m[1]] = r; });
      var popItems = (pop.items || []).filter(function (x) { return bySlug[x.slug]; });
      if (popItems.length >= 3) {
        var ol = ins.querySelector('[data-popular-list]');
        popItems.forEach(function (x, i) {
          var r = bySlug[x.slug], li = el('li', 'rank-item');
          li.appendChild(el('span', 'rank-no', String(i + 1)));
          var a = el('a', 'rank-link'); a.href = r.u;
          a.appendChild(el('span', 'rank-tick', r.k));
          a.appendChild(el('span', 'rank-title', r.t));
          li.appendChild(a);
          li.appendChild(el('span', 'rank-n muted', '조회 ' + num(x.n)));
          ol.appendChild(li);
        });
        ins.querySelector('[data-popular]').hidden = false;
        ins.hidden = false;
      }
      // 검색어를 사이트에 있는 종목에만 맞춰 보여 준다(엉뚱한 검색어·광고성 글자는 화면에 나오지 않음)
      var tick = {};
      idx.forEach(function (r) {
        var names = [r.k, r.c, r.e].concat(r.a || []).map(norm).filter(function (s) { return s.length >= 2; });
        if (!tick[r.k]) tick[r.k] = { k: r.k, c: r.c, names: [], n: 0 };
        tick[r.k].names = tick[r.k].names.concat(names);
      });
      (tr.items || []).forEach(function (x) {
        var q = norm(x.q);
        Object.keys(tick).forEach(function (k) {
          var t = tick[k];
          if (t.names.some(function (nm) { return nm === q || (q.length >= 2 && nm.indexOf(q) === 0); })) t.n += x.n;
        });
      });
      var hot = Object.keys(tick).map(function (k) { return tick[k]; }).filter(function (t) { return t.n > 0; })
        .sort(function (a, b) { return b.n - a.n; }).slice(0, 8);
      if (hot.length >= 3) {
        var ul = ins.querySelector('[data-trending-list]');
        hot.forEach(function (t, i) {
          var li = el('li'), a = el('a', 'chip'); a.href = base + '/t/' + t.k.toLowerCase() + '/';
          a.appendChild(el('strong', null, (i + 1) + ' ' + t.k));
          a.appendChild(document.createTextNode(' ' + t.c));
          li.appendChild(a); ul.appendChild(li);
        });
        ins.querySelector('[data-trending]').hidden = false;
        ins.hidden = false;
      }
    }).catch(function () {});
  }
})();
