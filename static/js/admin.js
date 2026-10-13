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
  function dayAgo(n) { return new Date(Date.now() + 9 * 3600e3 - n * 864e5).toISOString().slice(0, 10); }
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
  function heading(t, sub) { var h = el('h2', 'an-h2', t); if (sub) h.appendChild(el('span', 'muted an-h2-sub', ' ' + sub)); return h; }
  // 단계별 깔때기: 단계마다 막대 + 앞 단계 대비 전환율
  function funnel(title, steps, note) {
    var card = el('section', 'an-card an-funnel'); card.appendChild(el('h3', 'an-ct', title));
    if (note) card.appendChild(el('p', 'an-sub muted', note));
    var top = Math.max(1, steps[0][1] || 0);
    steps.forEach(function (st, i) {
      var row = el('div', 'fn-row');
      row.appendChild(el('span', 'fn-l', st[0]));
      var tr = el('span', 'fn-track'), f = el('span', 'fn-fill'); f.style.width = Math.max(st[1] ? 2 : 0, (st[1] || 0) / top * 100) + '%'; tr.appendChild(f); row.appendChild(tr);
      row.appendChild(el('span', 'fn-v', nf(st[1])));
      row.appendChild(el('span', 'fn-p muted', i ? pct(st[1], steps[i - 1][1]) : ''));
      card.appendChild(row);
    });
    return card;
  }
  var EVN = { share: '공유', save: '저장', like: '좋아요', repost: '리포스트', quote_open: '인용 창 열기', quote_submit: '인용 글 올림', follow_user: '사람 팔로우', follow_topic: '종목·테마 팔로우',
    compose_open: '글쓰기 상자 누름', post_submit: '글·댓글 올림', login_start: '로그인 시작', search: '검색', yt_play: '영상 재생', notif_open: '알림 열기',
    yt_jump_shown: '유튜브 바로가기 노출', yt_jump_click: '유튜브 바로가기 누름', featured_click: '이번 주 대표 글 누름',
    install_prompt: '설치 가능 표시', install_card: '설치 카드 노출', install_click: '설치 누름', install_accept: '설치 수락', install_dismiss: '설치 거절', installed: '설치 완료', ios_help: '아이폰 설치 안내' };

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
    var E = d.events || {}, EP = d.eventsPrev || {}, A = d.app || {};
    var inst = (E.installed || 0) + (E.install_accept && !E.installed ? E.install_accept : 0);
    k.appendChild(tile('앱 설치', nf(inst), '아이폰 안내 ' + nf(E.ios_help) + '회 별도', delta(inst, (EP.installed || 0))));
    k.appendChild(tile('앱 사용자', nf(A.users30), '최근 30일, 홈 화면 앱으로 연 기기'));
    k.appendChild(tile('앱 페이지뷰 비율', pct(A.pv, T.pv), nf(A.pv) + '회'));
    var co = (d.cohorts || []).filter(function (c) { return c.day <= dayAgo(7); }), cn = co.reduce(function (a, c) { return a + c.n; }, 0), c7 = co.reduce(function (a, c) { return a + c.d7; }, 0);
    var co1 = (d.cohorts || []).filter(function (c) { return c.day <= dayAgo(1); }), c1n = co1.reduce(function (a, c) { return a + c.n; }, 0), c1 = co1.reduce(function (a, c) { return a + c.d1; }, 0);
    k.appendChild(tile('재방문(다음 날 / 7일 안)', pct(c1, c1n) + ' / ' + pct(c7, cn), '처음 온 기기 중 다시 온 비율'));
    k.appendChild(tile('충성도(DAU/MAU)', pct(d.active.dau, d.active.mau), '높을수록 매일 오는 사람이 많음'));
    k.appendChild(tile('공유', nf(E.share), '기간 내 공유 누름', delta(E.share || 0, EP.share || 0)));
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

    // ---------- 전환·앱 ----------
    body.appendChild(heading('전환과 앱', '횟수 기준(같은 사람이 여러 번 하면 여러 번)'));
    var rpv = ((d.types || []).filter(function (x) { return x.t === 'r'; })[0] || {}).pv || 0;
    var reacts = (E.like || 0) + (E.share || 0) + (E.save || 0) + (E.repost || 0);
    var g4 = el('div', 'an-grid2');
    g4.appendChild(funnel('방문 → 가입 깔때기', [['방문(세션)', T.sess], ['리포트 읽음(페이지뷰)', rpv], ['반응(좋아요·공유·저장·리포스트)', reacts], ['로그인 시작', E.login_start || 0], ['가입 완료', T.signups]],
      '어느 단계에서 가장 많이 빠지는지 보면 다음에 손볼 곳이 보입니다.'));
    g4.appendChild(funnel('앱 설치 깔때기', [['설치 가능 표시(안드로이드·PC)', E.install_prompt || 0], ['설치 카드 노출', E.install_card || 0], ['설치 누름', E.install_click || 0], ['설치 완료', inst]],
      '아이폰은 설치 창을 띄울 수 없어 "아이폰 설치 안내"를 본 횟수만 따로 셉니다(' + nf(E.ios_help) + '회).'));
    var ed = {}; (d.eventsDaily || []).forEach(function (x) { (ed[x.day] = ed[x.day] || {})[x.ev] = x.n; });
    var sInst = d.series.map(function (r) { var e = ed[r.day] || {}; return { day: r.day, v: (e.installed || 0) || (e.install_accept || 0) }; });
    g4.appendChild(bars('일별 앱 설치', sInst, 'v', nf, { label: dayLabel, sub: function (t) { return '합계 ' + nf(t); } }));
    g4.appendChild(table('행동 이벤트', ['행동', '이번 기간', '앞 기간 대비'], Object.keys(EVN).filter(function (k2) { return E[k2] || EP[k2]; }).map(function (k2) {
      return [EVN[k2], nf(E[k2] || 0), delta(E[k2] || 0, EP[k2] || 0)];
    }).sort(function (a, b) { return 0; }), { note: '한 페이지에서 같은 행동은 한 번으로 셉니다.' }));
    body.appendChild(g4);

    // ---------- 리텐션 ----------
    body.appendChild(heading('재방문(리텐션)', '처음 온 날 기준, 최근 4주'));
    body.appendChild(table('처음 온 날별 재방문', ['처음 온 날', '새 기기', '다음 날 재방문', '7일 안 재방문'], (d.cohorts || []).slice().reverse().map(function (c) {
      return [c.day.slice(5).replace('-', '.'), nf(c.n), c.day <= dayAgo(1) ? pct(c.d1, c.n) : '집계 중', c.day <= dayAgo(7) ? pct(c.d7, c.n) : '집계 중'];
    }), { note: '방문 기록은 35일만 보관해서, 기록이 쌓이기 시작한 첫 주에는 예전부터 오던 사람도 "새 기기"로 잡힙니다.' }));

    // ---------- 콘텐츠 성과 ----------
    body.appendChild(heading('리포트 성과', '다음 영상·리포트 고를 때 참고'));
    body.appendChild(table('리포트별 성과', ['리포트', '페이지뷰', '평균 체류', '평균 스크롤', '첫 페이지', '좋아요', '댓글', '리포스트', '반응률'], (d.reports || []).map(function (x) {
      var r = x.likes + x.comments + x.reposts;
      return [link(titles[x.path] || x.path, base + x.path), nf(x.pv), dur(x.pv ? x.secs / x.pv : 0), x.scroll_n ? Math.round(x.scroll / x.scroll_n) + '%' : '–', nf(x.entries), nf(x.likes), nf(x.comments), nf(x.reposts), pct(r, x.pv)];
    }), { note: '반응률 = (좋아요+댓글+리포스트) ÷ 페이지뷰. 좋아요·댓글·리포스트는 전체 누적.' }));
    var g5 = el('div', 'an-grid2');
    g5.appendChild(table('첫 페이지 × 유입 경로', ['첫 페이지', '경로', '방문'], (d.entries || []).map(function (x) {
      var nm = titles[x.path] || (x.path === '/' ? '홈 피드' : x.path);
      return [link(nm, base + x.path), x.src === 'direct' ? '직접·북마크' : x.src, nf(x.n)];
    }), { note: '유튜브 영상 설명란·고정 댓글 링크가 어느 리포트로 사람을 데려왔는지 보입니다.' }));
    var thName = {}; document.querySelectorAll('.theme-nav a').forEach(function (a) { var m = /\/theme\/([^/]+)\//.exec(a.getAttribute('href')); if (m) thName[m[1]] = a.textContent.trim(); });
    g5.appendChild(table('팔로워 많은 종목·테마', ['종목·테마', '팔로워'], (d.topics || []).map(function (x) {
      return [x.kind === 't' ? link('$' + x.key, base + '/t/' + x.key.toLowerCase() + '/') : link('# ' + (thName[x.key] || x.key), base + '/theme/' + x.key + '/'), nf(x.n)];
    }), { note: '기간 내 새 종목·테마 팔로우 ' + nf(d.topicNew) + '건. 수요가 큰 종목은 다음 리포트 후보.' }));
    g5.appendChild(table('결과 없던 검색어', ['검색어', '사람 수'], (d.misses || []).map(function (x) { return [x.q, nf(x.n)]; }),
      { note: '사이트에 아직 리포트가 없는 종목을 찾은 것 — 새 리포트·영상 후보.' }));
    g5.appendChild(table('커뮤니티 활동(기간)', ['항목', '값'], [['리포스트', nf((d.actions || {}).reposts)], ['인용 글', nf((d.actions || {}).quotes)], ['종목·테마 팔로우', nf(d.topicNew)]]));
    body.appendChild(g5);

    // ---------- 기기·광고 ----------
    body.appendChild(heading('기기와 광고'));
    var g6 = el('div', 'an-grid2');
    var OSN = { ios: '아이폰·아이패드', android: '안드로이드', windows: '윈도우', mac: '맥', linux: '리눅스', other: '기타' };
    var BRN = { chrome: '크롬', safari: '사파리', samsung: '삼성 인터넷', edge: '엣지', firefox: '파이어폭스', kakaotalk: '카카오톡 안 브라우저', naver: '네이버 앱', youtube: '유튜브 앱', instagram: '인스타그램 앱', facebook: '페이스북 앱', whale: '웨일', other: '기타' };
    g6.appendChild(table('운영체제 × 브라우저', ['기기·브라우저', '페이지뷰', '비율', '방문'], (d.tech || []).map(function (x) {
      return [(OSN[x.os] || x.os) + ' · ' + (BRN[x.br] || x.br), nf(x.pv), share(x.pv, T.pv), nf(x.sess)];
    }), { note: '카카오톡·네이버 앱 안 브라우저 비율이 높으면 "외부 브라우저로 열기" 안내를 고려하세요.' }));
    var ad = {}; (d.adDaily || []).forEach(function (x) { ad[x.day] = x; });
    var sAd = d.series.map(function (r) { var x = ad[r.day] || {}; return { day: r.day, clicks: x.clicks || 0, imps: x.imps || 0 }; });
    g6.appendChild(bars('일별 쿠팡 상자 클릭', sAd, 'clicks', nf, { label: dayLabel, sub: function (t) { var im = sAd.reduce(function (a, x) { return a + x.imps; }, 0); return '클릭 ' + nf(t) + ' · 노출 ' + nf(im) + ' · 클릭률 ' + pct(t, im); } }));
    body.appendChild(g6);
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
