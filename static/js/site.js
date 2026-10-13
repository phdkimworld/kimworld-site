/* 김박사 월드 — 화면 동작 (프레임워크 없이, 없어도 글은 다 읽힘) */
(function () {
  'use strict';
  var root = document.documentElement;
  var base = (window.KW && window.KW.base) || '';

  // ---------- 저장소(사생활 모드 등에서 실패해도 동작) ----------
  function load(k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function setRaw(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) {} }

  var toastEl = document.querySelector('.toast'), toastTimer;
  function toast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg; toastEl.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 2200);
  }
  function track(name, params) { try { if (window.gtag) window.gtag('event', name, params || {}); } catch (e) {} }

  // ---------- 글자 크기 / 화면 테마 ----------
  var FONTS = ['', 'lg', 'xl'], FONT_NAMES = ['기본 글자', '큰 글자', '아주 큰 글자'];
  function cycleFont() {
    var i = (FONTS.indexOf(root.dataset.font || '') + 1) % FONTS.length;
    if (FONTS[i]) root.dataset.font = FONTS[i]; else delete root.dataset.font;
    setRaw('kw-font', FONTS[i] || null);
    toast(FONT_NAMES[i]);
  }
  function isDark() {
    if (root.dataset.theme) return root.dataset.theme === 'dark';
    return window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function toggleTheme() {
    var next = isDark() ? 'light' : 'dark';
    root.dataset.theme = next; setRaw('kw-theme', next);
    toast(next === 'dark' ? '어두운 화면' : '밝은 화면');
  }
  if (!root.dataset.theme && isDark()) root.dataset.theme = 'dark'; // 아이콘 표시용(저장은 안 함)

  // ---------- 리포트 ----------
  var report = document.querySelector('.report');
  var SAVED = 'kw-saved', RECENT = 'kw-recent';
  function current() {
    return report && { u: report.dataset.url, t: report.dataset.title, k: report.dataset.ticker, th: report.dataset.themeSlug || '' };
  }
  function isSaved() { var c = current(); return c && load(SAVED, []).some(function (x) { return x.u === c.u; }); }
  function syncSaveBtn() {
    var s = isSaved();
    document.querySelectorAll('[data-action="save"]').forEach(function (b) {
      b.setAttribute('aria-pressed', s ? 'true' : 'false');
      var l = b.querySelector('[data-save-label]'); if (l) l.textContent = s ? '저장됨' : '저장';
    });
  }
  function toggleSave() {
    var c = current(); if (!c) return;
    var list = load(SAVED, []).filter(function (x) { return x.u !== c.u; });
    var was = isSaved();
    if (!was) { c.at = Date.now(); list.unshift(c); }
    save(SAVED, list.slice(0, 50)); syncSaveBtn();
    toast(was ? '저장을 취소했습니다' : '저장했습니다. 아래 "내 정보 → 저장함"에서 찾을 수 있어요');
  }
  function share(btn) {
    var url = location.href.split('#')[0];
    var title = document.title;
    var su = btn && btn.getAttribute('data-share-url');
    if (su) { // 피드 카드의 공유 버튼: 그 리포트 주소
      var bp = (window.KW && KW.base) || '';
      url = location.origin + (bp && su.indexOf(bp + '/') !== 0 ? bp : '') + su;
      title = btn.getAttribute('data-share-title') || title;
    }
    if (navigator.share) {
      navigator.share({ title: title, url: url }).then(function () { track('share', { method: 'native' }); }).catch(function () {});
      return;
    }
    copy(url);
  }
  function copy(text) {
    var done = function () { toast('링크를 복사했습니다. 카카오톡에 붙여 넣으세요'); track('share', { method: 'copy' }); };
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(text).then(done, function () { prompt('아래 주소를 복사하세요', text); }); }
    else { prompt('아래 주소를 복사하세요', text); }
  }

  if (report) {
    // 최근 본 리포트 기록
    var c = current();
    // 읽은 기록(이 기기에만 저장): 내 프로필의 '읽은 리포트'와 광고 테마 맞춤에 쓴다
    var rec = load(RECENT, []).filter(function (x) { return x.u !== c.u; });
    c.at = Date.now(); rec.unshift(c); save(RECENT, rec.slice(0, 50));
    syncSaveBtn();

    // 숫자 기준일이 며칠 전인지
    var ageEl = document.querySelector('.asof-age');
    if (ageEl) {
      var d = new Date(ageEl.dataset.asof + 'T00:00:00');
      var days = Math.floor((Date.now() - d.getTime()) / 86400000);
      if (days >= 0) ageEl.textContent = days === 0 ? '오늘' : days < 60 ? days + '일 전' : Math.round(days / 30) + '개월 전';
    }

    // 읽은 위치 표시 막대 + 맨 위로 버튼 + 목차 강조
    var bar = document.querySelector('.progress span');
    var topBtn = document.querySelector('.to-top');
    var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.toc-side a'));
    var heads = tocLinks.map(function (a) { return document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1))); });
    var ticking = false;
    function onScroll() {
      ticking = false;
      var rect = report.getBoundingClientRect();
      var total = rect.height - window.innerHeight;
      var p = total > 0 ? Math.min(1, Math.max(0, -rect.top / total)) : 0;
      if (bar) bar.style.width = (p * 100).toFixed(1) + '%';
      if (topBtn) topBtn.classList.toggle('show', window.scrollY > 900);
      var active = -1;
      for (var i = 0; i < heads.length; i++) { if (heads[i] && heads[i].getBoundingClientRect().top < 140) active = i; }
      tocLinks.forEach(function (a, i) { a.classList.toggle('active', i === active); });
    }
    window.addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
    onScroll();

    // 용어 풀이
    var pop = document.querySelector('.term-pop'), openTerm = null;
    function closeTerm() { if (pop) pop.hidden = true; if (openTerm) openTerm.setAttribute('aria-expanded', 'false'); openTerm = null; }
    document.addEventListener('click', function (e) {
      var t = e.target.closest && e.target.closest('.term');
      if (!t) { if (!(e.target.closest && e.target.closest('.term-pop'))) closeTerm(); return; }
      if (openTerm === t) { closeTerm(); return; }
      closeTerm();
      pop.innerHTML = '';
      var s = document.createElement('strong'); s.textContent = t.textContent;
      var p = document.createElement('span'); p.textContent = t.dataset.def;
      pop.appendChild(s); pop.appendChild(p); pop.hidden = false;
      var r = t.getBoundingClientRect();
      var left = Math.min(window.scrollX + r.left, window.scrollX + document.documentElement.clientWidth - pop.offsetWidth - 16);
      pop.style.left = Math.max(16, left) + 'px';
      pop.style.top = (window.scrollY + r.bottom + 8) + 'px';
      t.setAttribute('aria-expanded', 'true'); openTerm = t;
      track('term_open', { term: t.textContent });
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeTerm(); });

    // 유튜브: 누를 때만 불러오기(페이지가 빨라짐)
    var yt = document.querySelector('.yt');
    if (yt) yt.querySelector('.yt-play').addEventListener('click', function () {
      var f = document.createElement('iframe');
      f.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(yt.dataset.yt) + '?autoplay=1&rel=0';
      f.title = '유튜브 영상'; f.allow = 'autoplay; encrypted-media; picture-in-picture'; f.allowFullscreen = true;
      yt.innerHTML = ''; yt.appendChild(f);
      track('video_play', { ticker: report.dataset.ticker });
    });

    // 쿠팡 클릭 측정
    document.querySelectorAll('[data-cp-slot]').forEach(function (a) {
      a.addEventListener('click', function () { track('coupang_click', { slot: a.dataset.cpSlot, ticker: report.dataset.ticker, theme: report.dataset.theme }); });
    });
  }

  // ---------- 버튼 ----------
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-action]');
    if (!b) return;
    var a = b.dataset.action;
    if (a === 'font') cycleFont();
    else if (a === 'theme') toggleTheme();
    else if (a === 'share') share(b);
    else if (a === 'save') toggleSave();
    else if (a === 'print') window.print();
    else if (a === 'top') window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // 애드핏 광고가 비면 자리를 접는다
  window.kwAdFail = function (el) { var box = el && el.closest ? el.closest('.ad') : null; if (box) box.classList.add('hidden'); };
  // 광고 차단기·네트워크 오류로 광고가 아예 안 뜨면 빈 '광고' 상자를 접는다(채울 광고가 없을 때는 위 kwAdFail이 처리)
  window.addEventListener('load', function () {
    setTimeout(function () {
      document.querySelectorAll('.ad-adfit, .ad-adsense').forEach(function (box) {
        var ins = box.querySelector('ins');
        // 광고가 채워지면 상자 안에 iframe이 생기거나(애드핏·애드센스) 숨겨 둔 ins가 보이게 바뀐다. 둘 다 아니면 빈 상자
        if (!ins || box.querySelector('iframe') || ins.getAttribute('data-ad-status') === 'filled' || (box.classList.contains('ad-adfit') && ins.style.display !== 'none')) return;
        box.classList.add('hidden');
      });
    }, 6000);
  });

  // ---------- 검색 ----------
  var results = document.querySelector('[data-results]');
  if (results) {
    var input = document.getElementById('q'), countEl = document.querySelector('.search-count');
    var CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ';
    function cho(s) {
      var out = '';
      for (var i = 0; i < s.length; i++) {
        var c = s.charCodeAt(i) - 0xac00;
        out += (c >= 0 && c < 11172) ? CHO[Math.floor(c / 588)] : s[i];
      }
      return out;
    }
    function norm(s) { return String(s || '').toLowerCase().replace(/[\s·\-_.,()]/g, ''); }
    var data = null;
    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    function card(r) {
      return '<article class="card"><a class="card-link" href="' + esc(r.u) + '"><div class="card-top"><span class="tick">' + esc(r.k) +
        '</span><span class="card-company">' + esc(r.c) + '</span><span class="card-theme">' + esc(r.th) + '</span></div><h3 class="card-title">' +
        esc(r.t) + '</h3><p class="card-summary">' + esc(r.s) + '</p><div class="card-meta">' + esc(r.d) + '</div></a></article>';
    }
    function run() {
      if (!data) return;
      var q = input.value.trim();
      var url = new URL(location.href);
      if (q) url.searchParams.set('q', q); else url.searchParams.delete('q');
      history.replaceState(null, '', url);
      if (!q) { results.innerHTML = ''; countEl.textContent = '리포트 ' + data.length + '개가 있습니다. 위에 검색어를 입력하세요.'; return; }
      var terms = q.split(/\s+/).map(norm).filter(Boolean);
      var choOnly = /^[ㄱ-ㅎ\s]+$/.test(q);
      var hits = data.map(function (r) {
        var hay = norm([r.k, r.c, r.e, (r.a || []).join(' '), r.th, r.t].join(' '));
        var hayCho = cho(norm(r.c + r.t + (r.a || []).join('')));
        var score = 0;
        for (var i = 0; i < terms.length; i++) {
          var t = terms[i];
          if (choOnly ? hayCho.indexOf(t) < 0 : hay.indexOf(t) < 0) return null;
          if (norm(r.k) === t || norm(r.c) === t) score += 10;
          else if (norm(r.k + r.c + (r.a || []).join('')).indexOf(t) >= 0) score += 5;
          else score += 1;
        }
        return { r: r, s: score };
      }).filter(Boolean).sort(function (a, b) { return b.s - a.s || (a.r.d < b.r.d ? 1 : -1); });
      countEl.textContent = hits.length ? '"' + q + '" 검색 결과 ' + hits.length + '개' : '"' + q + '"에 맞는 리포트가 아직 없습니다. 다른 이름이나 티커로 찾아보세요.';
      results.innerHTML = hits.slice(0, 50).map(function (h) { return card(h.r); }).join('');
      if (window.kwLogSearch) window.kwLogSearch(q, hits.length);
    }
    var timer;
    input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(run, 120); });
    input.value = new URLSearchParams(location.search).get('q') || '';
    fetch(base + '/search.json').then(function (r) { return r.json(); }).then(function (d) { data = d; run(); })
      .catch(function () { countEl.textContent = '검색 자료를 불러오지 못했습니다. 잠시 뒤 다시 시도하세요.'; });
  }

})();

// 접힌 상자(이벤트 카드·출처): 주소의 #앵커가 상자 안을 가리키면 펼치고, 인쇄할 때는 모두 펼친다
(function () {
  function openFor(hash) {
    if (!hash || hash.length < 2) return;
    var t = null; try { t = document.getElementById(decodeURIComponent(hash.slice(1))); } catch (e) {}
    for (var n = t; n; n = n.parentElement) if (n.tagName === 'DETAILS') n.open = true;
    if (t && t.tagName === 'DETAILS') { t.open = true; t.scrollIntoView(); }
  }
  openFor(location.hash);
  window.addEventListener('hashchange', function () { openFor(location.hash); });
  window.addEventListener('beforeprint', function () { document.querySelectorAll('details.fold').forEach(function (d) { d.open = true; }); });
})();

// 휴대폰에서 아래로 스크롤하면 머리글(로고·테마 줄)을 숨기고, 위로 조금이라도 올리면 다시 보인다
(function () {
  var h = document.querySelector('.site-header'); if (!h) return;
  var lastY = window.scrollY, tick = false;
  window.addEventListener('scroll', function () {
    if (tick) return; tick = true;
    requestAnimationFrame(function () {
      tick = false;
      var y = window.scrollY, dy = y - lastY;
      if (Math.abs(dy) < 6) return;
      h.classList.toggle('hdr-hide', dy > 0 && y > 160 && !h.contains(document.activeElement));
      lastY = y;
    });
  }, { passive: true });
})();

// 게시 날짜를 SNS처럼 '3시간 전', '2일 전'으로(30일이 넘으면 날짜 그대로)
(function () {
  var now = Date.now();
  document.querySelectorAll('time[data-ago]').forEach(function (t) {
    var d = new Date(t.getAttribute('datetime') + (t.getAttribute('datetime').length <= 10 ? 'T00:00:00+09:00' : ''));
    var s = (now - d.getTime()) / 1000; if (!(s >= 0)) return;
    var txt = s < 3600 ? '방금' : s < 86400 ? Math.floor(s / 3600) + '시간 전' : s < 86400 * 30 ? Math.floor(s / 86400) + '일 전' : null;
    if (txt) { t.title = t.textContent; t.textContent = txt; }
  });
})();

// 리포트: 휴대폰에서 위쪽 반응 줄이 화면 밖으로 나가면 아래 고정 줄을 띄운다(댓글 칸이 보이면 숨김)
(function () {
  var dock = document.querySelector('[data-dock]'), bar = document.querySelector('[data-report-bar]');
  if (!dock || !bar || !window.IntersectionObserver) return;
  var barOut = false, cmIn = false;
  var sync = function () { var on = barOut && !cmIn; dock.hidden = !on; document.body.classList.toggle('has-dock', on); };
  new IntersectionObserver(function (es) { barOut = !es[0].isIntersecting && es[0].boundingClientRect.top < 0; sync(); }).observe(bar);
  var cm = document.getElementById('comments');
  if (cm) new IntersectionObserver(function (es) { cmIn = es[0].isIntersecting; sync(); }).observe(cm);
})();

// 홈(휴대폰): 인사이트 칸을 피드 네 번째 글 뒤로 옮겨 첫 화면에 글이 먼저 보이게 한다(넓은 화면에서는 오른쪽 칸)
(function () {
  var side = document.querySelector('.home-side'), list = document.querySelector('.feed-list');
  if (!side || !list || !window.matchMedia) return;
  var home = side.parentNode, mq = matchMedia('(max-width: 999px)');
  function place() {
    if (mq.matches) {
      var posts = list.querySelectorAll(':scope > .post');
      var after = posts[3] || posts[posts.length - 1];
      if (after) { var nx = after.nextElementSibling; if (nx && nx.classList.contains('ad')) after = nx; after.after(side); }
    } else if (side.parentNode !== home) home.insertBefore(side, home.firstChild);
  }
  place();
  if (mq.addEventListener) mq.addEventListener('change', place);
})();

// ---------- 쿠팡 상자: 스스로 배우는 선택 + 성과 기록 ----------
// · 고르기: ad-weights.json(매시 빌드가 만드는 정적 파일)의 노출·클릭·수수료로 묶음마다 '기대 수익'을 추정한다.
//   톰슨 샘플링(베타 분포에서 클릭률을 뽑아 비교) → 잘 되는 묶음이 더 자주, 새 묶음도 계속 시험된다. 10%는 무작위로 탐색.
//   이용 환경(휴대폰/PC × 페이지 종류)과 자리별 성과를 반영하고, 이 브라우저에서 최근 읽은 테마의 상품을 조금 더 우대한다(기록은 이 기기에만).
// · 기록: 상자가 화면에 절반 이상 1초 보이면 노출, 상품을 누르면 클릭. 페이지를 떠날 때 한 번에 보낸다(API 부담 최소).
(function () {
  var KW = window.KW || {}, API = (KW.api || '').replace(/\/+$/, ''), base = KW.base || '';
  if (!document.querySelector('.ad-coupang-products, template[data-thread-ad]')) return;
  var mobile = window.matchMedia && matchMedia('(max-width: 759px)').matches;
  var path = location.pathname.slice(base.length);
  var pageType = document.querySelector('article.report') ? 'r' : /^\/(index\.html)?$/.test(path) ? 'h' : /^\/t\//.test(path) ? 't' : /^\/theme\//.test(path) ? 'th' : 'o';
  var SEG = (mobile ? 'm' : 'd') + '.' + pageType;
  var W = null, used = {}, queue = [], seenBox = new WeakSet();

  // 이 브라우저에서 최근 읽은 리포트의 테마(가까울수록 큰 값)
  var aff = {};
  try { (JSON.parse(localStorage.getItem('kw-recent') || '[]')).forEach(function (x, i) { if (x && x.th) aff[x.th] = (aff[x.th] || 0) + Math.max(0, 8 - i) / 8; }); } catch (e) {}

  function gamma(k) { // Marsaglia–Tsang
    if (k < 1) return gamma(k + 1) * Math.pow(Math.random(), 1 / k);
    var d = k - 1 / 3, c = 1 / Math.sqrt(9 * d), x, v, u;
    for (;;) {
      do { var u1 = Math.random(), u2 = Math.random(); x = Math.sqrt(-2 * Math.log(u1 || 1e-12)) * Math.cos(2 * Math.PI * u2); v = 1 + c * x; } while (v <= 0);
      v = v * v * v; u = Math.random();
      if (u < 1 - 0.0331 * x * x * x * x || Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
    }
  }
  function beta(a, b) { var x = gamma(a), y = gamma(b); return x / (x + y); }
  function score(sub, theme, slot) {
    var p = (W && W.prior) || { ctr: 0.02, n: 40 }, g = W && W.g && W.g[sub];
    var i = 0, c = 0;
    if (g) {
      i = g.i; c = g.c;
      var sg = g.s && g.s[SEG]; if (sg && sg[0] >= 30) { i = sg[0] + 0.3 * g.i; c = sg[1] + 0.3 * g.c; }   // 이 환경 자료가 충분하면 그쪽 위주
      var sl = g.l && g.l[slot]; if (sl && sl[0] >= 30) { i = 0.5 * i + sl[0]; c = 0.5 * c + sl[1]; }      // 이 자리 자료가 충분하면 반영
    }
    var ctr = beta(p.ctr * p.n + c, (1 - p.ctr) * p.n + Math.max(0, i - c));
    var val = 1; // 클릭 1번당 수수료(실적이 있으면): 묶음 값을 전체 평균 쪽으로 당겨서 쓴다
    if (W && W.epc > 0 && g) val = ((g.r || 0) + 20 * W.epc) / ((g.c || 0) + 20) / W.epc;
    var af = 1 + 0.5 * Math.min(1, (aff[theme] || 0) / 2);
    return ctr * val * af;
  }
  function subOf(gr) { return gr.getAttribute('data-cp-sub') || ''; }
  function showGroup(box, gr) {
    box.querySelectorAll('[data-cp-group]').forEach(function (x) { x.hidden = x !== gr; });
    var note = box.querySelector('[data-cp-note]'), dd = gr.getAttribute('data-cp-date');
    if (note) { note.hidden = !dd; var sp = note.querySelector('span'); if (sp) sp.textContent = dd || ''; }
  }
  // 상자 하나에 묶음 고르기(이미 이 페이지에 나온 묶음은 피한다)
  function choose(box) {
    var gs = Array.prototype.slice.call(box.querySelectorAll('[data-cp-group]'));
    if (!gs.length) return;
    var slot = box.getAttribute('data-slot') || '';
    var cand = gs.filter(function (g) { return !used[subOf(g)]; }); if (!cand.length) cand = gs;
    var pick;
    if (Math.random() < ((W && W.explore) || 0.1)) pick = cand[Math.floor(Math.random() * cand.length)];
    else { var best = -1; cand.forEach(function (g) { var sc = score(subOf(g), g.getAttribute('data-cp-theme') || '', slot); if (sc > best) { best = sc; pick = g; } }); }
    used[subOf(pick)] = 1; showGroup(box, pick);
  }
  function visibleGroup(box) { return box.querySelector('[data-cp-group]:not([hidden])'); }
  function inView(el) { var r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight; }

  // 노출 기록: 절반 이상 1초
  var io = window.IntersectionObserver ? new IntersectionObserver(function (es) {
    es.forEach(function (en) {
      var box = en.target;
      if (en.isIntersecting && en.intersectionRatio >= 0.5) {
        box._t = setTimeout(function () {
          if (seenBox.has(box)) return;
          var gr = visibleGroup(box); if (!gr) return;
          seenBox.add(box); queue.push({ g: subOf(gr), s: box.getAttribute('data-slot') || '', k: 'i' });
        }, 1000);
      } else clearTimeout(box._t);
    });
  }, { threshold: [0, 0.5] }) : null;
  function track(box) { if (io && !box._kw) { box._kw = 1; io.observe(box); } }
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('.cp-card'); if (!a) return;
    var box = a.closest('.ad-coupang-products'), gr = a.closest('[data-cp-group]'); if (!box || !gr) return;
    queue.push({ g: subOf(gr), s: box.getAttribute('data-slot') || '', k: 'c' });
    flush();
  }, true);
  function flush() {
    if (!queue.length || !API) return;
    var body = JSON.stringify({ seg: SEG, e: queue.splice(0, 40) });
    try { if (navigator.sendBeacon && navigator.sendBeacon(API + '/v1/ad/events', body)) return; } catch (e) {}
    try { fetch(API + '/v1/ad/events', { method: 'POST', body: body, keepalive: true, credentials: 'include' }); } catch (e) {}
  }
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') flush(); });
  window.addEventListener('pagehide', flush);

  // 대화 사이 광고(댓글·종토방)는 나중에 끼워지므로 community.js가 이걸 부른다
  window.kwAdNew = function (box) { if (!box) return; choose(box); track(box); };

  // 이 화면에서 실제로 보이는 상자부터 고른다(PC 전용 오른쪽 칸처럼 숨겨진 상자가 좋은 묶음을 먼저 가져가지 않게)
  var boxes = Array.prototype.slice.call(document.querySelectorAll('.ad-coupang-products'))
    .sort(function (a, b) { return (a.offsetParent === null) - (b.offsetParent === null); });
  boxes.forEach(function (b) { var g = visibleGroup(b); if (g) used[subOf(g)] = 1; track(b); });
  fetch(base + '/ad-weights.json', { cache: 'default' }).then(function (r) { return r.json(); }).then(function (w) {
    W = w; used = {};
    // 이미 화면에 보이는 상자는 바꾸지 않는다(깜빡임 방지). 나머지는 학습 자료로 다시 고른다
    boxes.forEach(function (b) { if (inView(b) || seenBox.has(b)) { var g = visibleGroup(b); if (g) used[subOf(g)] = 1; } });
    boxes.forEach(function (b) { if (!inView(b) && !seenBox.has(b)) choose(b); });
  }).catch(function () {
    boxes.forEach(function (b) { if (!inView(b)) choose(b); }); // 자료가 없으면 사전값(전체 평균)으로 고른다
  });
})();

// ---------- 방문 통계(운영자 애널리틱스): 페이지를 떠날 때 한 번만 보낸다 ----------
// 보내는 것: 주소(쿼리 제외)·유입 경로 종류(유튜브·구글…)·휴대폰 여부·이 기기 첫 방문 여부·이번 방문의 몇 번째 페이지·
// 실제로 보고 있던 시간(화면이 보이고 최근 30초 안에 움직임이 있던 초)·스크롤 깊이. 사람을 알아볼 정보는 없다.
(function () {
  var KW = window.KW || {}, API = (KW.api || '').replace(/\/+$/, '');
  if (!API || navigator.webdriver || /bot|crawl|spider|preview|lighthouse/i.test(navigator.userAgent)) return;
  var LS = function (k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
  var SS = function (k, v) { try { if (v === undefined) return sessionStorage.getItem(k); sessionStorage.setItem(k, v); } catch (e) { return null; } };
  if (LS('kw-noan') === '1') return; // 운영자가 '내 방문 빼기'를 켠 기기
  var isNew = !LS('kw-did');
  // 이번 방문(탭 세션)의 몇 번째 페이지인지, 처음 들어온 경로
  var n = (parseInt(SS('kw-sn'), 10) || 0) + 1; SS('kw-sn', String(n));
  var src = SS('kw-src');
  if (!src) {
    var h = '', u = new URLSearchParams(location.search).get('utm_source') || '';
    try { h = document.referrer ? new URL(document.referrer).hostname.toLowerCase() : ''; } catch (e) {}
    var map = [[/youtube\.com$|youtu\.be$/, 'youtube'], [/(^|\.)google\./, 'google'], [/naver\.com$/, 'naver'], [/daum\.net$|kakao\.com$/, 'kakao·daum'],
      [/bing\.com$/, 'bing'], [/(^|\.)(x|twitter|t)\.(com|co)$/, 'x'], [/facebook\.com$|fb\.com$/, 'facebook'], [/instagram\.com$/, 'instagram'], [/threads\.(net|com)$/, 'threads'],
      [/postype\.com$/, 'postype'], [/drkimworld\.com$/, 'direct']];
    src = u ? u.toLowerCase().replace(/[^a-z0-9.-]/g, '').slice(0, 40) : 'direct';
    if (!u && h) { src = h.replace(/^www\./, '').slice(0, 40); for (var i = 0; i < map.length; i++) if (map[i][0].test(h)) { src = map[i][1].replace('·', '-'); break; } }
    SS('kw-src', src);
  }
  var active = 0, last = Date.now(), maxSc = 0, sent = false;
  ['scroll', 'pointerdown', 'keydown', 'touchstart', 'mousemove'].forEach(function (e) { addEventListener(e, function () { last = Date.now(); }, { passive: true }); });
  setInterval(function () { if (document.visibilityState === 'visible' && Date.now() - last < 30000) active++; }, 1000);
  addEventListener('scroll', function () {
    var d = document.documentElement, max = d.scrollHeight - innerHeight;
    if (max > 0) maxSc = Math.max(maxSc, Math.round(Math.min(1, scrollY / max) * 100));
  }, { passive: true });
  function send() {
    if (sent) return; sent = true;
    var did = LS('kw-did') || '';
    var body = JSON.stringify({ p: location.pathname, r: src, m: matchMedia('(max-width: 759px)').matches ? 1 : 0, n: isNew ? 1 : 0, s: n, a: active, sc: maxSc });
    var url = API + '/v1/hit' + (/^[A-Za-z0-9_-]{22,64}$/.test(did) ? '?d=' + did : '');
    try { if (navigator.sendBeacon && navigator.sendBeacon(url, body)) return; } catch (e) {}
    try { fetch(url, { method: 'POST', body: body, keepalive: true, credentials: 'include' }); } catch (e) {}
  }
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') send(); });
  addEventListener('pagehide', send);
})();
