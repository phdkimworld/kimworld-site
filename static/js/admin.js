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
  var TYPE = { h: '홈 피드', r: '리포트', t: '종목·커뮤니티', th: '테마', p: '글 상세', u: '프로필', s: '검색', o: '기타' };

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
    sortable(t);
    return card;
  }
  // 표 정렬: 머리 칸을 누르면 그 열로 정렬(숫자 열은 큰 것부터, 글자 열은 가나다순부터), 다시 누르면 반대로
  function cellKey(td) {
    var t = (td.textContent || '').replace(/\s+/g, ' ').trim(), m;
    if (!t || t === '–' || t === '-' || /집계 중|자료 없음/.test(t)) return null;
    if ((m = /^(?:(\d+)시간 ?)?(?:(\d+)분 ?)?(?:(\d+)초)?$/.exec(t)) && (m[1] || m[2] || m[3])) return (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0);
    if ((m = /^([▲▼+-])?\s*\$?(\d[\d,]*(?:\.\d+)?)/.exec(t))) { var v = parseFloat(m[2].replace(/,/g, '')); return m[1] === '▼' || m[1] === '-' ? -v : v; }
    return t;
  }
  function sortable(t) {
    var ths = Array.prototype.slice.call(t.querySelectorAll('thead th')), tb = t.querySelector('tbody');
    Array.prototype.forEach.call(tb.rows, function (r, i) { r._i = i; });
    var cur = -1, dir = 0;
    ths.forEach(function (th, col) {
      th.classList.add('an-sort'); th.tabIndex = 0; th.setAttribute('role', 'button'); th.title = '눌러서 정렬';
      var go = function () {
        var rows = Array.prototype.slice.call(tb.rows);
        var keys = rows.map(function (r) { return r.cells[col] ? cellKey(r.cells[col]) : null; });
        var numeric = keys.filter(function (k) { return typeof k === 'number'; }).length >= keys.filter(function (k) { return typeof k === 'string'; }).length;
        dir = cur === col ? -dir : (numeric ? -1 : 1); cur = col; // 처음 누르면 숫자는 내림차순, 글자는 오름차순
        rows.map(function (r, i) { return { r: r, k: keys[i] }; }).sort(function (a, b) {
          var x = a.k, y = b.k;
          if (x === null && y === null) return a.r._i - b.r._i;
          if (x === null) return 1; if (y === null) return -1; // 빈 칸은 늘 아래
          var c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'ko');
          return (c || (a.r._i - b.r._i) * dir) * dir;
        }).forEach(function (o) { tb.appendChild(o.r); });
        ths.forEach(function (h, j) { h.setAttribute('aria-sort', j === col ? (dir > 0 ? 'ascending' : 'descending') : 'none'); });
      };
      th.addEventListener('click', go);
      th.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });
  }
  function share(v, total) { // 표 안 비율 막대(값은 글자로, 막대는 보조)
    var w = el('span', 'an-share'), f = el('span', 'an-share-f'); f.style.width = (total ? Math.max(2, v / total * 100) : 0) + '%';
    w.appendChild(f); w.appendChild(el('span', 'an-share-t', pct(v, total))); return w;
  }
  function delta(cur, prev, invert) {
    if (!prev) { var nd = el('span', 'an-d muted', delta.short ? '–' : '비교 자료 없음'); nd.title = '앞 기간 자료 없음'; return nd; }
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
    yt_jump_shown: '유튜브 바로가기 노출', yt_jump_click: '유튜브 바로가기 누름', featured_click: '홈 대표 글(조회수 상위) 누름', home_report: '홈에서 리포트 누름', home_post: '홈에서 커뮤니티 글 누름', fig_click: '리포트 그림 누름', sent_vote: '투자 심리 투표', sent_vote_feed: '피드 카드에서 투표', mid_next_click: '본문 중간 함께 읽기 누름', mood_rank: '검색 화면 투자 심리 순위 바꿔 봄', poll_share: '투표 상자 공유', next_bar: '읽는 중 아래 줄 다음 리포트 누름', update_request: '종목 리포트 업데이트 요청', share_kakao: '카카오톡으로 공유', poll_comment: '투표 상자에서 의견 남기기 누름', push_on: '푸시 알림 켬',
    install_prompt: '설치 가능 표시', install_card: '설치 카드 노출', install_click: '설치 누름', install_accept: '설치 수락', install_dismiss: '설치 거절', installed: '설치 완료', ios_help: '아이폰 설치 안내', signup: '가입 완료', dm_send: '쪽지 보냄', dm_open: '쪽지함 열기', avatar_set: '프로필 사진 바꿈', block: '차단', quote_share: '문장 인용 공유', quote_card: '인용 카드 만들기',
    install_bar: '설치 안내 줄 노출', install_inapp: '앱 안 브라우저→크롬 열기', ic_header: '설치 누름: 머리줄', ic_footer: '설치 누름: 바닥글', ic_bar: '설치 누름: 안내 줄', ic_report: '설치 누름: 리포트 끝', ic_feed: '설치 누름: 홈 피드' };

  // ---------- 유입 분석: 이름표·색(채널 순서 고정, 색은 채널을 따라감) ----------
  var CH_ORDER = ['search', 'youtube', 'direct', 'messenger', 'social', 'community', 'ai', 'referral', 'app', 'other'];
  var CHN = { app: '앱(홈 화면·푸시)', search: '검색', youtube: '유튜브', direct: '직접·북마크', messenger: '메신저·공유 링크', social: 'SNS', community: '커뮤니티·블로그', ai: 'AI 답변', referral: '다른 사이트', email: '이메일', internal: '사이트 안(새 탭)', other: '기타' };
  var chKey = function (c) { return CH_ORDER.indexOf(c) >= 0 ? c : 'other'; };
  var SRCN = { 'naver-search': '네이버 검색', 'naver-blog': '네이버 블로그', 'naver-cafe': '네이버 카페', 'naver-finance': '네이버 증권·뉴스', 'naver-kin': '네이버 지식iN', 'naver-etc': '네이버 기타',
    'naver-app': '네이버 앱', 'google-search': '구글 검색', 'google-discover': '구글 디스커버', 'google-news': '구글 뉴스', 'google-etc': '구글 기타', 'daum-search': '다음 검색', 'daum-cafe': '다음 카페',
    'daum-etc': '다음 기타', 'daum-app': '다음 앱', 'kakao-web': '카카오(웹)', kakaotalk: '카카오톡 공유', line: '라인', band: '밴드', telegram: '텔레그램', bing: '빙', duckduckgo: '덕덕고', yahoo: '야후', zum: '줌',
    youtube: '유튜브', share: '공유 링크', 'share-kakaotalk': '공유 → 카카오톡', 'share-instagram': '공유 → 인스타그램', 'share-facebook': '공유 → 페이스북', 'share-line': '공유 → 라인', 'share-naver': '공유 → 네이버 앱', 'share-threads': '공유 → 스레드', x: 'X(트위터)', threads: '스레드', instagram: '인스타그램', facebook: '페이스북', tiktok: '틱톡', linkedin: '링크드인', reddit: '레딧', chatgpt: 'ChatGPT', perplexity: '퍼플렉시티',
    gemini: '제미나이', claude: 'Claude', copilot: '코파일럿', dcinside: '디시인사이드', fmkorea: '에펨코리아', clien: '클리앙', ppomppu: '뽐뿌', theqoo: '더쿠', ruliweb: '루리웹', paxnet: '팍스넷',
    stocktwits: '스톡트윗츠', tistory: '티스토리', brunch: '브런치', postype: '포스타입', velog: '벨로그', investing: '인베스팅닷컴', toss: '토스', email: '이메일', direct: '직접·북마크', internal: '사이트 안(새 탭)', 'app-home': '홈 화면 앱 아이콘', push: '푸시 알림', app: '앱' };
  var srcName = function (x) { return SRCN[x] || x; };
  function swatch(ch) { var s = el('span', 'an-sw ch-' + chKey(ch)); s.setAttribute('aria-hidden', 'true'); return s; }
  function chLabel(ch) { var w = el('span', 'an-chl'); w.appendChild(swatch(ch)); w.appendChild(document.createTextNode(CHN[ch] || ch)); return w; }
  function legend(keys) { var l = el('div', 'an-legend'); keys.forEach(function (k) { var i = el('span', 'an-li'); i.appendChild(swatch(k)); i.appendChild(document.createTextNode(CHN[k] || k)); l.appendChild(i); }); return l; }
  // 쌓은 막대(날짜별 채널 구성). 막대 사이·조각 사이 2px 틈, 마우스를 올리면 그날 구성
  function stacked(title, days, byDay, keys, sub) {
    var card = el('section', 'an-card an-chart'); card.appendChild(el('h3', 'an-ct', title));
    if (sub) card.appendChild(el('p', 'an-sub muted', sub));
    card.appendChild(legend(keys));
    var W = 600, H = 170, pad = 18, totals = days.map(function (d) { return keys.reduce(function (a, k) { return a + ((byDay[d] || {})[k] || 0); }, 0); });
    var max = Math.max(1, Math.max.apply(null, totals));
    var ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + (H + pad)); svg.setAttribute('class', 'an-svg'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', title + ' 쌓은 막대 차트');
    [0.5, 1].forEach(function (f) {
      var y = H - H * f, ln = document.createElementNS(ns, 'line'); ln.setAttribute('x1', 0); ln.setAttribute('x2', W); ln.setAttribute('y1', y); ln.setAttribute('y2', y); ln.setAttribute('class', 'an-grid'); svg.appendChild(ln);
      var tx = document.createElementNS(ns, 'text'); tx.setAttribute('x', 2); tx.setAttribute('y', y + 12); tx.setAttribute('class', 'an-axis'); tx.textContent = nf(Math.round(max * f)); svg.appendChild(tx);
    });
    var bw = W / days.length, gap = Math.min(2, bw * 0.2);
    days.forEach(function (d, i) {
      var g = document.createElementNS(ns, 'g'), y = H, parts = [];
      var hit = document.createElementNS(ns, 'rect'); hit.setAttribute('x', i * bw); hit.setAttribute('y', 0); hit.setAttribute('width', bw); hit.setAttribute('height', H); hit.setAttribute('class', 'an-hit'); g.appendChild(hit);
      keys.forEach(function (k) {
        var v = (byDay[d] || {})[k] || 0; if (!v) return;
        var h = H * v / max, r = document.createElementNS(ns, 'rect');
        r.setAttribute('x', i * bw + gap / 2); r.setAttribute('y', y - h + (y < H ? 1 : 0)); r.setAttribute('width', Math.max(1, bw - gap)); r.setAttribute('height', Math.max(1, h - (y < H ? 1 : 0)));
        r.setAttribute('class', 'an-seg ch-' + k); g.appendChild(r); y -= h; parts.push((CHN[k] || k) + ' ' + nf(v));
      });
      var label = d.slice(5).replace('-', '.') + ' · 합계 ' + nf(totals[i]) + (parts.length ? '\n' + parts.join(' · ') : '');
      g.addEventListener('mousemove', function (e) { tip.textContent = label; tip.hidden = false; tip.style.left = (e.clientX + 12) + 'px'; tip.style.top = (e.clientY - 34) + 'px'; });
      g.addEventListener('mouseleave', function () { tip.hidden = true; });
      svg.appendChild(g);
    });
    var lt = document.createElementNS(ns, 'text'), rt = document.createElementNS(ns, 'text');
    lt.setAttribute('x', 0); lt.setAttribute('y', H + 14); lt.setAttribute('class', 'an-axis'); lt.textContent = days[0].slice(5).replace('-', '.');
    rt.setAttribute('x', W); rt.setAttribute('y', H + 14); rt.setAttribute('text-anchor', 'end'); rt.setAttribute('class', 'an-axis'); rt.textContent = days[days.length - 1].slice(5).replace('-', '.');
    svg.appendChild(lt); svg.appendChild(rt); card.appendChild(svg);
    return card;
  }
  // 유입 분석 섹션 전체
  function acquisition(d, T) {
    var A = d.acq; if (!A) return null;
    var wrap = el('div', 'an-acq');
    wrap.appendChild(heading('유입 분석', '어디서 와서, 얼마나 읽고, 무엇을 했는지'));
    var total = A.channels.reduce(function (a, x) { return a + x.sess; }, 0);
    if (!total) { wrap.appendChild(el('p', 'muted an-empty', '세분화 유입 자료는 이 기능을 켠 날부터 쌓입니다. 내일 다시 보세요.')); return wrap; }
    var prevCh = {}; (A.channelsPrev || []).forEach(function (x) { prevCh[x.ch] = x.sess; });
    var bounce = function (x) { return x.sess ? pct(x.sess - x.multi, x.sess) : '–'; };
    var perSess = function (x) { return x.sess ? (x.pv / x.sess).toFixed(1) : '–'; };
    var secSess = function (x) { return dur(x.sess ? x.secs / x.sess : 0); };
    // 핵심 숫자: 가장 큰 채널, 검색 비율, 유튜브 비율, 메신저 공유
    var top = A.channels[0], by = {}; A.channels.forEach(function (x) { by[x.ch] = x; });
    var tl = el('div', 'an-tiles');
    tl.appendChild(tile('가장 큰 유입', CHN[top.ch] || top.ch, pct(top.sess, total) + ' · ' + nf(top.sess) + '회', delta(top.sess, prevCh[top.ch] || 0)));
    ['search', 'youtube', 'messenger', 'ai'].forEach(function (c) {
      var x = by[c] || { sess: 0, multi: 0, secs: 0, pv: 0 };
      tl.appendChild(tile(CHN[c] + ' 유입', pct(x.sess, total), nf(x.sess) + '회 · 이탈 ' + bounce(x), delta(x.sess, prevCh[c] || 0)));
    });
    var best = A.channels.filter(function (x) { return x.sess >= 5; }).sort(function (a, b) { return b.secs / b.sess - a.secs / a.sess; })[0];
    if (best) tl.appendChild(tile('가장 오래 읽는 유입', CHN[best.ch] || best.ch, '방문당 ' + secSess(best) + ' · ' + perSess(best) + '페이지'));
    wrap.appendChild(tl);
    // 일별 채널 구성
    var keys = [], byDay = {};
    A.daily.forEach(function (x) { var k = chKey(x.ch); (byDay[x.day] = byDay[x.day] || {})[k] = ((byDay[x.day] || {})[k] || 0) + x.sess; if (keys.indexOf(k) < 0) keys.push(k); });
    keys.sort(function (a, b) { return CH_ORDER.indexOf(a) - CH_ORDER.indexOf(b); });
    var g = el('div', 'an-grid2');
    g.appendChild(stacked('일별 방문 — 채널 구성', d.series.map(function (r) { return r.day; }), byDay, keys, '막대에 마우스를 올리면 그날 채널별 방문 수'));
    // 요일별
    var DOW = ['일', '월', '화', '수', '목', '금', '토'], dw = DOW.map(function (n, i) { return { d: n, v: 0 }; });
    (A.dow || []).forEach(function (x) { dw[x.dow].v += x.sess; });
    var dwRows = [1, 2, 3, 4, 5, 6, 0].map(function (i) { return { day: DOW[i] + '요일', v: dw[i].v }; });
    g.appendChild(bars('요일별 방문', dwRows, 'v', nf, { label: function (r) { return r.day; }, sub: function () { var b = dwRows.slice().sort(function (a, b) { return b.v - a.v; })[0]; return '가장 많은 요일: ' + b.day; } }));
    wrap.appendChild(g);
    // 채널 표
    delta.short = true;
    wrap.appendChild(table('채널별 성과', ['채널', '방문', '비율', '앞 기간 대비', '처음 온 비율', '이탈률', '3페이지 이상', '방문당 페이지', '방문당 체류', '30초 이상 읽은 페이지', '휴대폰'],
      A.channels.map(function (x) {
        return [chLabel(x.ch), nf(x.sess), share(x.sess, total), delta(x.sess, prevCh[x.ch] || 0), pct(x.newv, x.sess), bounce(x), pct(x.deep, x.sess), perSess(x), secSess(x), pct(x.engaged, x.pv), pct(x.mob, x.sess)];
      }), { note: '방문 = 세션(첫 페이지 기준). 이탈률 = 한 페이지만 보고 나간 비율. 체류 = 화면을 실제로 보고 있던 시간.' }));
    // 세부 출처(채널로 거르기)
    var srcCard = el('section', 'an-card');
    srcCard.appendChild(el('h3', 'an-ct', '세부 출처별 성과와 전환'));
    srcCard.appendChild(el('p', 'an-sub muted', '네이버 검색·블로그·카페, 구글 검색·디스커버, 카카오톡 공유처럼 나눠 봅니다. 가입·설치·공유는 그 출처로 들어온 방문에서 일어난 횟수.'));
    var chips = el('div', 'an-chips'), holder = el('div');
    var chList = ['all'].concat(A.channels.map(function (x) { return x.ch; }));
    function drawSrc(filter) {
      holder.textContent = '';
      var rows = A.sources.filter(function (x) { return filter === 'all' || x.ch === filter; }).map(function (x) {
        var e = x.ev || {}, inst = (e.installed || 0) || (e.install_accept || 0);
        return [srcName(x.src), chLabel(x.ch), nf(x.sess), share(x.sess, total), delta(x.sess, x.prevSess), pct(x.newv, x.sess), bounce(x), perSess(x), secSess(x),
          nf(e.signup || 0), pct(e.signup || 0, x.sess), nf(inst), nf(e.login_start || 0), nf(e.share || 0)];
      });
      var t = table('', ['출처', '채널', '방문', '비율', '대비', '처음 온', '이탈률', '페이지', '체류', '가입', '가입률', '앱 설치', '로그인 시작', '공유'], rows);
      t.querySelector('.an-ct').remove(); t.className = 'an-inner';
      holder.appendChild(t);
    }
    chList.forEach(function (c, i) {
      var b = el('button', 'an-chip', c === 'all' ? '전체' : (CHN[c] || c)); b.type = 'button'; b.setAttribute('aria-pressed', i ? 'false' : 'true');
      if (c !== 'all') b.insertBefore(swatch(c), b.firstChild);
      b.addEventListener('click', function () { chips.querySelectorAll('.an-chip').forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); }); drawSrc(c); });
      chips.appendChild(b);
    });
    srcCard.appendChild(chips); srcCard.appendChild(holder); drawSrc('all');
    wrap.appendChild(srcCard);
    // 유튜브 영상별(리포트 = 영상)
    var name = function (path) { return titles[path] || ({ '/': '홈 피드', '/p/': '글 상세', '/u/': '프로필', '/search/': '검색', '/(기타)': '기타 페이지' })[path] || path; };
    var g2 = el('div', 'an-grid2');
    g2.appendChild(table('들어온 사이트(도메인)', ['도메인', '방문', '비율'], A.refs.map(function (x) { return [x.host, nf(x.sess), share(x.sess, total)]; }),
      { note: '주소의 도메인만 기록합니다(검색어·전체 주소는 브라우저가 보내지 않음). 처음 보는 사이트가 보이면 어디서 링크됐는지 확인해 보세요.' }));
    // 링크 위치별(설명란·고정 댓글·영상 속 안내…) 성과. 종목·영상(캠페인)은 합쳐서 본다
    var POS = { pinned: '고정 댓글', comment: '고정 댓글', desc: '설명란', description: '설명란', midroll: '영상 속 안내', endcard: '엔드 카드', end: '엔드 카드', card: '카드', shorts: '쇼츠', bio: '프로필 링크', post: '게시물', quote: '인용 카드', link: '링크', video: '영상', '-': '(위치 없음)' };
    var pos = function (v) { return POS[v] ? POS[v] + (POS[v] !== v && v !== '-' ? ' (' + v + ')' : '') : v; };
    g2.appendChild(table('링크 위치별 유입(UTM)', ['출처 / 매체', '위치', '방문', '계속 읽은 비율', '방문당 체류', '종목·영상 수'], A.campaigns.map(function (x) {
      return [x.src + ' / ' + pos(x.med), pos(x.cont), nf(x.sess), pct(x.multi, x.sess), dur(x.sess ? x.secs / x.sess : 0), nf(x.camps || 0)];
    }), { note: '종목·영상(utm_campaign)은 합쳐서 위치(utm_content)별로 봅니다. 링크 끝에 ?utm_source=youtube&utm_medium=video&utm_content=pinned 처럼 붙이면 설명란·고정 댓글·영상 속 안내를 나눠 볼 수 있습니다. 유튜브 매체는 롱폼 video, 쇼츠 shorts로 나뉩니다.' }));
    wrap.appendChild(g2);
    return wrap;
  }

  // ---------- 신고 처리: 신고된 쪽지·프로필 사진·닉네임/소개. 쪽지는 신고된 것만 여기서 본다 ----------
  function reportsPanel(box) {
    api('/v1/admin/reports').then(function (d) {
      if (d._status !== 200) return;
      var dm = d.dm || [], us = d.users || [];
      if (!dm.length && !us.length) return;
      box.appendChild(heading('신고 처리', '쪽지 ' + dm.length + '건 · 프로필 ' + us.length + '건'));
      var API = C.apiBase;
      var act = function (path, body, row) { return function () { api(path, { method: 'POST', body: body }).then(function (r) { if (r.ok) { row.style.opacity = .4; row.querySelectorAll('button').forEach(function (b) { b.disabled = true; }); } }); }; };
      var g = el('div', 'an-grid2');
      if (dm.length) {
        var c1 = el('section', 'an-card'); c1.appendChild(el('h3', 'an-ct', '신고된 쪽지'));
        c1.appendChild(el('p', 'an-sub muted', '가리면 받은 사람 화면에서 "운영자가 가린 쪽지"로 바뀝니다. 같은 사람이 계속 신고되면 계정 정지(Moderate의 ban)도 고려하세요. 보낸 사람은 신고가 3명 이상이면 처음 보는 사람에게 쪽지를 못 보냅니다.'));
        dm.forEach(function (m) {
          var row = el('div', 'an-rep');
          var h = el('div', 'an-rep-h'); h.appendChild(link(m.sender_nick || ('#' + m.sender), base + '/u/?id=' + m.sender)); h.appendChild(el('span', 'muted', ' · 신고 ' + m.n + '명 · ' + new Date(m.created).toLocaleString('ko-KR') + (m.status !== 'ok' ? ' · ' + m.status : '')));
          row.appendChild(h); row.appendChild(el('p', 'an-rep-b', m.body || '(지워진 쪽지)'));
          var r = el('div', 'kw-row');
          r.appendChild(C.btn('가리기', 'btn btn-small', act('/v1/admin/dm/' + m.id, { status: 'hidden' }, row)));
          r.appendChild(C.btn('문제 없음', 'btn btn-small', act('/v1/admin/dm/' + m.id, { status: 'ok' }, row)));
          row.appendChild(r); c1.appendChild(row);
        });
        g.appendChild(c1);
      }
      if (us.length) {
        var c2 = el('section', 'an-card'); c2.appendChild(el('h3', 'an-ct', '신고된 프로필'));
        c2.appendChild(el('p', 'an-sub muted', '사진은 3명이 신고하면 자동으로 내려갑니다. 문제없으면 되돌리세요.'));
        us.forEach(function (u) {
          var row = el('div', 'an-rep');
          var h = el('div', 'an-rep-h');
          if (u.what === 'avatar' && u.av_stored) { var im = new Image(); im.src = API + '/v1/avatar/' + u.id + '?raw=1&t=' + Date.now(); im.width = im.height = 56; im.className = 'an-rep-img'; im.alt = '신고된 사진'; h.appendChild(im); }
          h.appendChild(link(u.nick, base + '/u/?id=' + u.id));
          h.appendChild(el('span', 'muted', ' · ' + (u.what === 'avatar' ? '사진' : '닉네임·소개') + ' 신고 ' + u.n + '명' + (u.what === 'avatar' ? (u.av ? ' · 지금 보임' : ' · 내려감') : '')));
          row.appendChild(h);
          if (u.what === 'profile' && u.bio) row.appendChild(el('p', 'an-rep-b', '소개: ' + u.bio));
          var r = el('div', 'kw-row');
          if (u.what === 'avatar') {
            r.appendChild(C.btn('사진 지우기', 'btn btn-small', act('/v1/admin/users/' + u.id + '/avatar', { action: 'remove' }, row)));
            r.appendChild(C.btn('문제 없음(되돌리기)', 'btn btn-small', act('/v1/admin/users/' + u.id + '/avatar', { action: 'restore' }, row)));
          } else {
            r.appendChild(C.btn('소개 지우기', 'btn btn-small', act('/v1/admin/users/' + u.id + '/profile', { action: 'clear_bio' }, row)));
            r.appendChild(C.btn('문제 없음', 'btn btn-small', act('/v1/admin/users/' + u.id + '/profile', { action: 'ok' }, row)));
          }
          row.appendChild(r); c2.appendChild(row);
        });
        g.appendChild(c2);
      }
      box.appendChild(g);
    }).catch(function () {});
  }

  function render(d) {
    body.textContent = '';
    var T = d.totals, P = d.prev, CM = d.community;
    var avg = T.pv ? T.secs / T.pv : 0, pavg = P.pv ? P.secs / P.pv : 0;
    var info = el('p', 'muted an-info', d.since + ' ~ 오늘 (' + d.days + '일, 한국 날짜) · ' + new Date(d.generated).toLocaleString('ko-KR') + ' 기준' + (d.days > 30 ? ' · 방문자 수는 최근 35일만 보관' : ''));
    var BT = d.bots || {}, btN = (BT.ua || 0) + (BT.dc || 0) + (BT.idle || 0);
    if (btN) info.textContent += ' · 봇으로 보고 뺀 페이지뷰 ' + nf(btN) + '(봇 이름표 ' + nf(BT.ua || 0) + ' · 데이터센터 망 ' + nf(BT.dc || 0) + ' · 반응 없음 ' + nf(BT.idle || 0) + ')';
    if (BT.quick) info.textContent += ' · 15초 안에 무반응으로 나간 페이지 ' + nf(BT.quick) + '(그중 첫 페이지 ' + nf(BT.quick_land || 0) + ', 페이지뷰에는 넣지 않음)';
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
    k.appendChild(tile('새 글', nf(CM.board), '답글 ' + nf(CM.replies) + ' · 리포트 공유·인용 ' + nf(CM.report)));
    // 홈은 입구 페이지라 체류 시간보다 '홈에서 리포트로 넘어간 비율'이 핵심(홈 페이지뷰 대비 리포트 누름)
    var Eh = d.events || {}, homePv = ((d.pages || []).filter(function (x) { return x.path === '/'; })[0] || {}).pv || 0;
    k.appendChild(tile('홈 → 리포트 클릭률', pct(Eh.home_report || 0, homePv), '홈 페이지뷰 ' + nf(homePv) + ' 중 리포트 누름 ' + nf(Eh.home_report) + ' · 글 누름 ' + nf(Eh.home_post)));
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
    var rbox = el('div'); body.appendChild(rbox); reportsPanel(rbox);

    var g = el('div', 'an-grid2');
    var dayLabel = function (r) { return r.day.slice(5).replace('-', '.'); };
    g.appendChild(bars('일별 방문자', d.series, 'uv', nf, { label: dayLabel, sub: function () { return '기간 합계(중복 제외) ' + nf(T.uv) + '명'; } }));
    g.appendChild(bars('일별 페이지뷰', d.series, 'pv', nf, { label: dayLabel, sub: function (t) { return '합계 ' + nf(t); } }));
    var sAvg = d.series.map(function (r) { return { day: r.day, v: r.pv ? r.secs / r.pv : 0 }; });
    g.appendChild(bars('일별 평균 체류시간', sAvg, 'v', function (v) { return dur(v); }, { label: dayLabel, sub: function () { return '기간 평균 ' + dur(avg); } }));
    // 방문당 페이지 수(그날 페이지뷰 ÷ 세션). 광고 노출 기회를 가장 직접 보여 주는 수익 지표(2026-10-20 운영자 요청)
    var sPps = d.series.map(function (r) { return { day: r.day, v: r.sess ? r.pv / r.sess : 0 }; });
    g.appendChild(bars('일별 방문당 페이지 수', sPps, 'v', function (v) { return v ? v.toFixed(2) : '0'; }, { label: dayLabel, sub: function () { return '기간 평균 ' + (T.sess ? (T.pv / T.sess).toFixed(2) : '0') + '쪽'; } }));
    // 일별 광고 노출: 화면에 절반 이상 1초 보인 광고 상자 수(종류별 합). 애드핏 자체 집계(렌더 기준)와는 다르다
    var edA = {}; (d.eventsDaily || []).forEach(function (x) { if (/^adv_/.test(x.ev)) (edA[x.day] = edA[x.day] || {})[x.ev.slice(4)] = x.n; });
    var advK = { adfit: '애드핏', coupang: '쿠팡', adsense: '애드센스', dable: '데이블' };
    var sAdv = d.series.map(function (r) { var e = edA[r.day] || {}, t = 0; Object.keys(advK).forEach(function (k) { t += e[k] || 0; }); return { day: r.day, v: t, e: e }; });
    g.appendChild(bars('일별 광고 노출(화면에 보인 광고)', sAdv, 'v', nf, { label: dayLabel, sub: function (t) {
      var by = {}; sAdv.forEach(function (x) { Object.keys(x.e).forEach(function (k) { by[k] = (by[k] || 0) + x.e[k]; }); });
      return '합계 ' + nf(t) + (Object.keys(by).length ? ' · ' + Object.keys(by).map(function (k) { return (advK[k] || k) + ' ' + nf(by[k]); }).join(' · ') : '') + ' · 페이지뷰당 ' + (T.pv ? (t / T.pv).toFixed(2) : '0') + '개';
    } }));
    g.appendChild(bars('일별 가입자', d.series, 'signups', nf, { label: dayLabel, sub: function (t) { return '합계 ' + nf(t) + '명'; } }));
    g.appendChild(bars('일별 새 커뮤니티 글', d.series, 'board', nf, { label: dayLabel, sub: function (t) { return '합계 ' + nf(t) + '개'; } }));
    var hours = []; for (var h = 0; h < 24; h++) hours.push({ h: h, pv: 0 });
    (d.hours || []).forEach(function (x) { hours[x.h].pv = x.pv; });
    g.appendChild(bars('시간대별 페이지뷰 (한국 시각)', hours, 'pv', nf, { label: function (r) { return r.h + '시'; }, sub: function () { return '가장 많은 시간 ' + hours.slice().sort(function (a, b) { return b.pv - a.pv; })[0].h + '시'; } }));
    // 미국 동부시간: 한국 시각 기록(날짜+시)을 실제 시각으로 바꿔 뉴욕 시간으로 다시 묶는다(서머타임 자동 반영)
    var hoursEt = []; for (var he = 0; he < 24; he++) hoursEt.push({ h: he, pv: 0 });
    var etFmt = null; try { etFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', hourCycle: 'h23' }); } catch (e) {}
    if (etFmt && (d.hoursDay || []).length) {
      d.hoursDay.forEach(function (x) {
        var t = new Date(x.day + 'T' + (x.h < 10 ? '0' : '') + x.h + ':30:00+09:00');
        var hh = parseInt(etFmt.format(t), 10) % 24; if (hoursEt[hh]) hoursEt[hh].pv += x.pv;
      });
      g.appendChild(bars('시간대별 페이지뷰 (미국 동부시간)', hoursEt, 'pv', nf, { label: function (r) { return r.h + '시'; }, sub: function () { return '가장 많은 시간 ' + hoursEt.slice().sort(function (a, b) { return b.pv - a.pv; })[0].h + '시 (ET)'; } }));
    }
    body.appendChild(g);

    var acq = acquisition(d, T); delta.short = false; if (acq) body.appendChild(acq);

    var g2 = el('div', 'an-grid2');
    g2.appendChild(table('유입 경로(간단, 예전부터 쌓인 자료)', ['경로', '방문', '비율', '이탈률', '처음 온 비율'], (d.sources || []).map(function (s) {
      return [s.src === 'direct' ? '직접·북마크' : s.src, nf(s.sess), share(s.sess, T.sess), pct(s.sess - s.multi, s.sess), pct(s.newv, s.sess)];
    }), { note: '방문의 첫 페이지 기준. 영상 설명란 링크는 youtube로 잡힙니다.' }));
    g2.appendChild(table('페이지 종류', ['종류', '페이지뷰', '비율', '평균 체류', '휴대폰'], (d.types || []).map(function (x) {
      return [TYPE[x.t] || x.t, nf(x.pv), share(x.pv, T.pv), dur(x.pv ? x.secs / x.pv : 0), pct(x.mob, x.pv)];
    })));
    body.appendChild(g2);

    body.appendChild(table('많이 본 페이지', ['페이지', '페이지뷰', '평균 체류', '첫 페이지', '평균 스크롤'], (d.pages || []).map(function (x) {
      var m = /^\/(t|theme)\/([^/]+)\/$/.exec(x.path);
      var name = titles[x.path] || ({ '/': '홈 피드', '/p/': '글 상세(모든 글)', '/u/': '프로필', '/search/': '검색', '/(기타)': '기타 페이지' })[x.path]
        || (m ? (m[1] === 't' ? m[2].toUpperCase() + ' 종목·커뮤니티' : '테마: ' + m[2]) : x.path);
      return [link(name, x.path === '/(기타)' ? '#' : base + x.path), nf(x.pv), dur(x.pv ? x.secs / x.pv : 0), nf(x.entries), x.scroll_n ? Math.round(x.scroll / x.scroll_n) + '%' : '–'];
    }), { note: '평균 스크롤: 페이지를 어디까지 내려 읽었는지(맨 끝 = 100%).' }));

    var g3 = el('div', 'an-grid2');
    g3.appendChild(table('커뮤니티', ['항목', '값'], [
      ['전체 가입자', nf(CM.users)], ['정지 계정', nf(CM.banned)], ['기간 내 글 쓴 사람', nf(CM.writers)],
      ['새 커뮤니티 글', nf(CM.board)], ['답글', nf(CM.replies)], ['리포트 공유·인용 글', nf(CM.report)],
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
    g4.appendChild(funnel('앱 설치 깔때기', [['설치 가능 표시(안드로이드·PC)', E.install_prompt || 0], ['설치 카드·안내 줄 노출', (E.install_card || 0) + (E.install_bar || 0)], ['설치 누름', E.install_click || 0], ['설치 완료', inst]],
      '아이폰은 설치 창을 띄울 수 없어 "아이폰 설치 안내"를 본 횟수만 따로 셉니다(' + nf(E.ios_help) + '회).'));
    var ed = {}; (d.eventsDaily || []).forEach(function (x) { (ed[x.day] = ed[x.day] || {})[x.ev] = x.n; });
    var sInst = d.series.map(function (r) { var e = ed[r.day] || {}; return { day: r.day, v: (e.installed || 0) || (e.install_accept || 0) }; });
    g4.appendChild(bars('일별 앱 설치', sInst, 'v', nf, { label: dayLabel, sub: function (t) { return '합계 ' + nf(t); } }));
    g4.appendChild(table('행동 이벤트', ['행동', '이번 기간', '앞 기간 대비'], Object.keys(EVN).filter(function (k2) { return E[k2] || EP[k2]; }).map(function (k2) {
      return [EVN[k2], nf(E[k2] || 0), delta(E[k2] || 0, EP[k2] || 0)];
    }).sort(function (a, b) { return 0; }), { note: '한 페이지에서 같은 행동은 한 번으로 셉니다.' }));
    body.appendChild(g4);

    // ---------- 투자 심리 투표 ----------
    var SV = d.sentiment;
    if (SV) {
      body.appendChild(heading('투자 심리 투표', '종목 화면·리포트·피드 카드의 불리시/베어리시'));
      var kv = el('div', 'an-tiles');
      kv.appendChild(tile('투표 수', nf(SV.votes), '한 사람·한 종목 하루 한 표', delta(SV.votes, SV.prevVotes)));
      kv.appendChild(tile('참여자', nf(SV.voters), '기기·계정 기준(중복 제외)', delta(SV.voters, SV.prevVoters)));
      kv.appendChild(tile('2일 이상 참여', SV.voters ? pct(SV.repeat, SV.voters) : '–', nf(SV.repeat) + '명이 다른 날 다시 투표'));
      kv.appendChild(tile('방문 대비 참여', T.uv ? pct(SV.voters, T.uv) : '–', '기간 방문자 중 한 번이라도 투표'));
      kv.appendChild(tile('피드에서 투표', E.sent_vote ? pct(E.sent_vote_feed || 0, E.sent_vote) : '–', '투표한 페이지 중 피드 카드에서 누른 비율'));
      kv.appendChild(tile('투표 받은 종목', nf(SV.tickers), ''));
      body.appendChild(kv);
      var gs = el('div', 'an-grid2');
      gs.appendChild(bars('일별 참여자', SV.daily, 'voters', nf, { label: dayLabel, sub: function () { return '기간 합계(중복 제외) ' + nf(SV.voters) + '명'; } }));
      gs.appendChild(table('종목별 투표', ['종목', '투표', '강세(불리시) 표', '강세 : 약세'], (SV.top || []).map(function (x) {
        var n = (x.bull || 0) + (x.bear || 0);
        return [link(x.ticker, base + '/t/' + String(x.ticker).toLowerCase() + '/'), nf(n), nf(x.bull), n ? Math.round(x.bull / n * 100) + ' : ' + Math.round(x.bear / n * 100) : '–'];
      }), { note: '기간 안의 강세:약세 표 비율입니다. 종목 화면에 보이는 지수는 최근 30일 기준입니다.' }));
      body.appendChild(gs);
    }

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
    var osAgg = {}; (d.tech || []).forEach(function (x) { var o = osAgg[x.os] || (osAgg[x.os] = { pv: 0, sess: 0 }); o.pv += x.pv || 0; o.sess += x.sess || 0; });
    g6.appendChild(table('운영체제', ['운영체제', '페이지뷰', '비율', '방문'], Object.keys(osAgg).sort(function (a, b) { return osAgg[b].pv - osAgg[a].pv; }).map(function (k) {
      return [OSN[k] || k, nf(osAgg[k].pv), share(osAgg[k].pv, T.pv), nf(osAgg[k].sess)];
    })));
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
