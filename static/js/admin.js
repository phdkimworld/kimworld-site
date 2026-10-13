// 운영 통계(/admin/): 운영자 계정으로 로그인했을 때만 API가 자료를 준다.
(function () {
  var C = window.KWC, root = document.querySelector('[data-admin]');
  if (!root) return;
  var msg = root.querySelector('[data-an-msg]'), gate = root.querySelector('[data-an-gate]'), body = root.querySelector('[data-an-body]'), ctl = root.querySelector('[data-an-ctl]');
  if (!C) { msg.textContent = '통계 서버가 꺼져 있습니다.'; return; }
  var api = C.api, el = C.el, base = (window.KW || {}).base || '';
  var days = 30, titles = {};
  var nf = function (n) { return Number(n || 0).toLocaleString('ko-KR'); };
  var pct = function (a, b) { return b ? Math.round(a / b * 1000) / 10 + '%' : '–'; };
  var dur = function (s) { s = Math.round(s || 0); return s >= 60 ? Math.floor(s / 60) + '분 ' + (s % 60) + '초' : s + '초'; };
  var TYPE = { h: '홈 피드', r: '리포트', t: '종목·종토방', th: '테마', p: '글 상세', u: '프로필', s: '검색', o: '기타' };

  // 이 기기 방문 빼기
  var noan = root.querySelector('[data-an-noan]');
  try { noan.checked = localStorage.getItem('kw-noan') === '1'; } catch (e) {}
  noan.addEventListener('change', function () { try { localStorage.setItem('kw-noan', noan.checked ? '1' : '0'); } catch (e) {} });

  fetch(base + '/search.json').then(function (r) { return r.json(); }).then(function (idx) {
    (idx || []).forEach(function (r) { var m = String(r.u).match(/\/r\/[^/]+\/?$/); if (m) titles[m[0].replace(/\/?$/, '/')] = r.k + ' · ' + String(r.t).replace(/^.*?(주가|가격) 내러티브와 패턴 투자전략:\s*/, ''); });
  }).catch(function () {});

  // ---------- 차트: 막대 하나짜리 시계열(축 하나, 색 하나), 마우스를 올리면 값 ----------
  var tip = el('div', 'an-tip'); tip.hidden = true; document.body.appendChild(tip);
  function bars(title, rows, key, fmt, opt) {
    opt = opt || {};
    var card = el('section', 'an-card an-chart'); card.appendChild(el('h3', 'an-ct', title));
    var total = rows.reduce(function (a, r) { return a + (r[key] || 0); }, 0);
    if (opt.sub) card.appendChild(el('p', 'an-sub muted', opt.sub(total)));
    var W = 600, H = 150, pad = 18, max = Math.max(1, Math.max.apply(null, rows.map(function (r) { return r[key] || 0; })));
    var ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + (H + pad)); svg.setAttribute('class', 'an-svg'); svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', title + ' 막대 차트');
    [0.5, 1].forEach(function (f) { // 옅은 눈금선 2개
      var y = H - H * f, ln = document.createElementNS(ns, 'line');
      ln.setAttribute('x1', 0); ln.setAttribute('x2', W); ln.setAttribute('y1', y); ln.setAttribute('y2', y); ln.setAttribute('class', 'an-grid'); svg.appendChild(ln);
      var tx = document.createElementNS(ns, 'text'); tx.setAttribute('x', 2); tx.setAttribute('y', y + 12); tx.setAttribute('class', 'an-axis'); tx.textContent = fmt(max * f); svg.appendChild(tx);
    });
    var bw = W / rows.length, gap = Math.min(2, bw * 0.2);
    rows.forEach(function (r, i) {
      var v = r[key] || 0, h = Math.max(v ? 2 : 0, H * v / max);
      var g = document.createElementNS(ns, 'g');
      var hit = document.createElementNS(ns, 'rect'); // 마우스 잡는 자리는 막대보다 넓게
      hit.setAttribute('x', i * bw); hit.setAttribute('y', 0); hit.setAttribute('width', bw); hit.setAttribute('height', H); hit.setAttribute('class', 'an-hit');
      var b = document.createElementNS(ns, 'rect');
      b.setAttribute('x', i * bw + gap / 2); b.setAttribute('y', H - h); b.setAttribute('width', Math.max(1, bw - gap)); b.setAttribute('height', h);
      b.setAttribute('rx', Math.min(3, (bw - gap) / 2)); b.setAttribute('class', 'an-bar');
      g.appendChild(hit); g.appendChild(b);
      var label = (opt.label ? opt.label(r) : r.day) + ' · ' + fmt(v);
      g.addEventListener('mousemove', function (e) { tip.textContent = label; tip.hidden = false; tip.style.left = (e.clientX + 12) + 'px'; tip.style.top = (e.clientY - 34) + 'px'; b.classList.add('on'); });
      g.addEventListener('mouseleave', function () { tip.hidden = true; b.classList.remove('on'); });
      svg.appendChild(g);
    });
    var lt = document.createElementNS(ns, 'text'), rt = document.createElementNS(ns, 'text');
    lt.setAttribute('x', 0); lt.setAttribute('y', H + 14); lt.setAttribute('class', 'an-axis'); lt.textContent = opt.label ? opt.label(rows[0]) : rows[0].day.slice(5);
    rt.setAttribute('x', W); rt.setAttribute('y', H + 14); rt.setAttribute('text-anchor', 'end'); rt.setAttribute('class', 'an-axis'); rt.textContent = opt.label ? opt.label(rows[rows.length - 1]) : rows[rows.length - 1].day.slice(5);
    svg.appendChild(lt); svg.appendChild(rt);
    card.appendChild(svg);
    return card;
  }
  function table(title, head, rows, opt) {
    opt = opt || {};
    var card = el('section', 'an-card'); card.appendChild(el('h3', 'an-ct', title));
    if (opt.note) card.appendChild(el('p', 'an-sub muted', opt.note));
    if (!rows.length) { card.appendChild(el('p', 'muted an-empty', '아직 자료가 없습니다.')); return card; }
    var wrap = el('div', 'an-tw'), t = el('table', 'an-table'), tr = el('tr');
    head.forEach(function (h, i) { var th = el('th', i ? 'num' : '', h); tr.appendChild(th); });
    var thead = el('thead'); thead.appendChild(tr); t.appendChild(thead);
    var tb = el('tbody');
    rows.forEach(function (r) {
      var row = el('tr');
      r.forEach(function (c, i) {
        var td = el('td', i ? 'num' : '');
        if (c && c.nodeType) td.appendChild(c); else td.textContent = c;
        row.appendChild(td);
      });
      tb.appendChild(row);
    });
    t.appendChild(tb); wrap.appendChild(t); card.appendChild(wrap);
    return card;
  }
  function share(v, total) { // 표 안 비율 막대(값은 글자로, 막대는 보조)
    var w = el('span', 'an-share'), f = el('span', 'an-share-f'); f.style.width = (total ? Math.max(2, v / total * 100) : 0) + '%';
    w.appendChild(f); w.appendChild(el('span', 'an-share-t', pct(v, total))); return w;
  }
  function delta(cur, prev, invert) {
    if (!prev) return el('span', 'an-d muted', '비교 자료 없음');
    var d = (cur - prev) / prev * 100, up = d >= 0;
    var s = el('span', 'an-d ' + ((up !== !!invert) ? 'good' : 'bad'), (up ? '▲ ' : '▼ ') + Math.abs(Math.round(d)) + '%');
    s.title = '바로 앞 같은 기간: ' + nf(prev); return s;
  }
  function tile(label, value, sub, d) {
    var t = el('div', 'an-tile'); t.appendChild(el('span', 'an-tl', label)); t.appendChild(el('strong', 'an-tv', value));
    var row = el('span', 'an-ts'); if (d) row.appendChild(d); if (sub) row.appendChild(el('span', 'muted', sub)); t.appendChild(row);
    return t;
  }
  function link(text, href) { var a = el('a', null, text); a.href = href; return a; }

  function render(d) {
    body.textContent = '';
    var T = d.totals, P = d.prev, CM = d.community;
    var avg = T.pv ? T.secs / T.pv : 0, pavg = P.pv ? P.secs / P.pv : 0;
    var info = el('p', 'muted an-info', d.since + ' ~ 오늘 (' + d.days + '일, 한국 날짜) · ' + new Date(d.generated).toLocaleString('ko-KR') + ' 기준' + (d.days > 30 ? ' · 방문자 수는 최근 35일만 보관' : ''));
    body.appendChild(info);

    var k = el('div', 'an-tiles');
    k.appendChild(tile('방문자', nf(T.uv), '기기 기준', delta(T.uv, P.uv)));
    k.appendChild(tile('페이지뷰', nf(T.pv), '', delta(T.pv, P.pv)));
    k.appendChild(tile('방문(세션)', nf(T.sess), '', delta(T.sess, P.sess)));
    k.appendChild(tile('평균 체류시간', dur(avg), '페이지당 실제로 본 시간', delta(avg, pavg)));
    k.appendChild(tile('방문당 페이지', T.sess ? (T.pv / T.sess).toFixed(2) : '–', ''));
    k.appendChild(tile('이탈률', T.sess ? pct(T.sess - T.multi, T.sess) : '–', '한 페이지만 보고 나감', P.sess ? delta(1 - T.multi / Math.max(1, T.sess), 1 - P.multi / P.sess, true) : null));
    k.appendChild(tile('처음 온 방문', pct(T.newv, T.sess), nf(T.newv) + '회'));
    k.appendChild(tile('휴대폰 비율', pct(T.mob, T.pv), ''));
    k.appendChild(tile('가입자', nf(CM.users), '기간 내 신규 ' + nf(T.signups), delta(T.signups, P.signups)));
    k.appendChild(tile('오늘 / 7일 / 30일 방문자', nf(d.active.dau) + ' / ' + nf(d.active.wau) + ' / ' + nf(d.active.mau), 'DAU · WAU · MAU'));
    k.appendChild(tile('새 글', nf(CM.board), '답글 ' + nf(CM.replies) + ' · 리포트 댓글 ' + nf(CM.report)));
    k.appendChild(tile('검토 대기', nf((CM.held || 0) + (CM.hidden || 0)), '보류 ' + nf(CM.held) + ' · 신고 숨김 ' + nf(CM.hidden)));
    body.appendChild(k);

    var g = el('div', 'an-grid2');
    var dayLabel = function (r) { return r.day.slice(5).replace('-', '.'); };
    g.appendChild(bars('일별 방문자', d.series, 'uv', nf, { label: dayLabel, sub: function () { return '기간 합계(중복 제외) ' + nf(T.uv) + '명'; } }));
    g.appendChild(bars('일별 페이지뷰', d.series, 'pv', nf, { label: dayLabel, sub: function (t) { return '합계 ' + nf(t); } }));
    var sAvg = d.series.map(function (r) { return { day: r.day, v: r.pv ? r.secs / r.pv : 0 }; });
    g.appendChild(bars('일별 평균 체류시간', sAvg, 'v', function (v) { return dur(v); }, { label: dayLabel, sub: function () { return '기간 평균 ' + dur(avg); } }));
    g.appendChild(bars('일별 가입자', d.series, 'signups', nf, { label: dayLabel, sub: function (t) { return '합계 ' + nf(t) + '명'; } }));
    g.appendChild(bars('일별 새 글(종토방·라운지)', d.series, 'board', nf, { label: dayLabel, sub: function (t) { return '합계 ' + nf(t) + '개'; } }));
    var hours = []; for (var h = 0; h < 24; h++) hours.push({ h: h, pv: 0 });
    (d.hours || []).forEach(function (x) { hours[x.h].pv = x.pv; });
    g.appendChild(bars('시간대별 페이지뷰 (한국 시각)', hours, 'pv', nf, { label: function (r) { return r.h + '시'; }, sub: function () { return '가장 많은 시간 ' + hours.slice().sort(function (a, b) { return b.pv - a.pv; })[0].h + '시'; } }));
    body.appendChild(g);

    var g2 = el('div', 'an-grid2');
    g2.appendChild(table('유입 경로', ['경로', '방문', '비율', '이탈률', '처음 온 비율'], (d.sources || []).map(function (s) {
      return [s.src === 'direct' ? '직접·북마크' : s.src, nf(s.sess), share(s.sess, T.sess), pct(s.sess - s.multi, s.sess), pct(s.newv, s.sess)];
    }), { note: '방문의 첫 페이지 기준. 영상 설명란 링크는 youtube로 잡힙니다.' }));
    g2.appendChild(table('페이지 종류', ['종류', '페이지뷰', '비율', '평균 체류', '휴대폰'], (d.types || []).map(function (x) {
      return [TYPE[x.t] || x.t, nf(x.pv), share(x.pv, T.pv), dur(x.pv ? x.secs / x.pv : 0), pct(x.mob, x.pv)];
    })));
    body.appendChild(g2);

    body.appendChild(table('많이 본 페이지', ['페이지', '페이지뷰', '평균 체류', '첫 페이지', '평균 스크롤'], (d.pages || []).map(function (x) {
      var m = /^\/(t|theme)\/([^/]+)\/$/.exec(x.path);
      var name = titles[x.path] || ({ '/': '홈 피드', '/p/': '글 상세(모든 글)', '/u/': '프로필', '/search/': '검색', '/(기타)': '기타 페이지' })[x.path]
        || (m ? (m[1] === 't' ? m[2].toUpperCase() + ' 종목·종토방' : '테마: ' + m[2]) : x.path);
      return [link(name, x.path === '/(기타)' ? '#' : base + x.path), nf(x.pv), dur(x.pv ? x.secs / x.pv : 0), nf(x.entries), x.scroll_n ? Math.round(x.scroll / x.scroll_n) + '%' : '–'];
    }), { note: '평균 스크롤: 페이지를 어디까지 내려 읽었는지(맨 끝 = 100%).' }));

    var g3 = el('div', 'an-grid2');
    g3.appendChild(table('커뮤니티', ['항목', '값'], [
      ['전체 가입자', nf(CM.users)], ['정지 계정', nf(CM.banned)], ['기간 내 글 쓴 사람', nf(CM.writers)],
      ['새 글(종토방·라운지)', nf(CM.board)], ['답글', nf(CM.replies)], ['리포트 댓글', nf(CM.report)],
      ['리포트 좋아요', nf(CM.postLikes)], ['팔로우(전체 / 기간 내)', nf(CM.follows) + ' / ' + nf(CM.newFollows)]
    ]));
    g3.appendChild(table('활발한 사용자', ['닉네임', '글', '받은 좋아요', '팔로워'], (d.topUsers || []).filter(function (u) { return u.posts; }).map(function (u) {
      return [link(u.nick, base + '/u/?id=' + u.id), nf(u.posts), nf(u.likes), nf(u.followers)];
    })));
    g3.appendChild(table('사이트 검색어', ['검색어', '사람 수'], (d.searches || []).map(function (s) { return [s.q, nf(s.n)]; }), { note: '하루 한 사람 한 번만 셈' }));
    g3.appendChild(table('광고 자리별 성과', ['자리', '노출', '클릭', '클릭률'], (d.ads || []).map(function (a) {
      return [a.slot, nf(a.imps), nf(a.clicks), pct(a.clicks, a.imps)];
    }), { note: '쿠팡 상자. 노출 = 화면에 절반 이상 1초' }));
    body.appendChild(g3);
    body.hidden = false;
  }

  function load() {
    msg.hidden = false; msg.textContent = '불러오는 중…';
    return api('/v1/admin/analytics?days=' + days).then(function (d) {
      if (d._status !== 200) { msg.textContent = d.message || '불러오지 못했습니다.'; return; }
      msg.hidden = true; render(d);
    }).catch(function () { msg.textContent = '불러오지 못했습니다. 잠시 뒤 새로고침해 주세요.'; });
  }
  root.querySelectorAll('[data-days]').forEach(function (b) {
    b.addEventListener('click', function () {
      days = +b.getAttribute('data-days');
      root.querySelectorAll('[data-days]').forEach(function (x) { x.setAttribute('aria-selected', x === b ? 'true' : 'false'); });
      load();
    });
  });
  root.querySelector('[data-an-reload]').addEventListener('click', load);

  api('/v1/admin/whoami').then(function (w) {
    if (!w.loggedIn) { msg.textContent = '운영자 계정으로 로그인해 주세요.'; gate.hidden = false; return; }
    if (!w.owner) {
      msg.textContent = w.user ? '이 계정(' + w.user.nick + ')은 운영자로 지정되어 있지 않습니다.' : '닉네임을 먼저 정해 주세요.';
      if (!w.user) gate.hidden = false;
      return;
    }
    ctl.hidden = false; load();
  }).catch(function () { msg.textContent = '통계 서버에 연결하지 못했습니다.'; });
})();
