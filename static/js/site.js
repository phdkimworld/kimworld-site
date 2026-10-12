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
    return report && { u: report.dataset.url, t: report.dataset.title, k: report.dataset.ticker };
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
    if (!was) list.unshift(c);
    save(SAVED, list.slice(0, 50)); syncSaveBtn();
    toast(was ? '저장을 취소했습니다' : '저장했습니다. 홈의 "이어서 읽기"에서 찾을 수 있어요');
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
    var rec = load(RECENT, []).filter(function (x) { return x.u !== c.u; });
    rec.unshift(c); save(RECENT, rec.slice(0, 8));
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

  // ---------- 홈: 이어서 읽기 ----------
  var rv = document.querySelector('.recent-viewed');
  if (rv) {
    var saved = load(SAVED, []), recent = load(RECENT, []);
    var seen = {}, items = [];
    saved.forEach(function (x) { if (!seen[x.u]) { seen[x.u] = 1; items.push({ x: x, s: true }); } });
    recent.forEach(function (x) { if (!seen[x.u]) { seen[x.u] = 1; items.push({ x: x, s: false }); } });
    if (items.length) {
      var ul = rv.querySelector('[data-recent]');
      items.slice(0, 8).forEach(function (it) {
        var li = document.createElement('li'), a = document.createElement('a');
        a.href = it.x.u; a.textContent = (it.s ? '★ ' : '') + it.x.k + ' · ' + it.x.t;
        li.appendChild(a); ul.appendChild(li);
      });
      rv.hidden = false;
    }
  }

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

  // 쿠팡 상품 묶음: 방문마다 하나를 무작위로 보여 준다(검색어별 노출을 고르게 나눠 클릭을 비교하려고)
  // 한 페이지에 상자가 여럿이면 시작점만 무작위로 정하고 차례로 다른 묶음을 보여 준다(같은 상품이 두 번 보이지 않게)
  var cpStart = Math.floor(Math.random() * 1000);
  document.querySelectorAll('.cp-rot').forEach(function (box, bi) {
    var gs = box.querySelectorAll('[data-cp-group]');
    if (gs.length < 2) return;
    var pick = (cpStart + bi) % gs.length;
    gs.forEach(function (g, i) { g.hidden = i !== pick; });
    var note = box.parentNode && box.parentNode.querySelector('[data-cp-note]'), dd = gs[pick].getAttribute('data-cp-date');
    if (note) { note.hidden = !dd; note.querySelector('span').textContent = dd || ''; }
  });
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
