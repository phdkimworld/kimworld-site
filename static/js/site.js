// 행동 이벤트(운영 통계용): 이 페이지에서 일어난 일의 이름만 모았다가, 페이지를 떠날 때 방문 기록과 함께 한 번 보낸다
window.kwEvents = window.kwEvents || {};
window.kwEv = function (name) { window.kwEvents[name] = 1; };

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
  root.dataset.theme = 'dark'; // 화면은 검은 바탕 하나(예전에 저장한 밝은 화면 설정은 무시)
  setRaw('kw-theme', null);

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
    kwEv('save');
    var list = load(SAVED, []).filter(function (x) { return x.u !== c.u; });
    var was = isSaved();
    if (!was) { c.at = Date.now(); list.unshift(c); }
    save(SAVED, list.slice(0, 50)); syncSaveBtn();
    toast(was ? '저장을 취소했습니다' : '저장했습니다. 아래 "내 정보 → 저장함"에서 찾을 수 있어요');
  }
  // 공유 주소에 utm_source=share를 붙여 공유로 들어온 방문을 따로 센다(유입 분석 '공유')
  function shareUrl(u) { u = u.split('#')[0].replace(/[?&]utm_[a-z]+=[^&]*/g, '').replace(/\?$/, ''); return u + (u.indexOf('?') < 0 ? '?' : '&') + 'utm_source=share&utm_medium=link'; }
  window.kwShareUrl = shareUrl;
  function share(btn) {
    kwEv('share');
    var url = location.href.split('#')[0];
    var ogt = document.querySelector('meta[property="og:title"]');
    var title = (ogt && ogt.content) || document.title;
    var su = btn && btn.getAttribute('data-share-url');
    if (su) { // 피드 카드의 공유 버튼: 그 리포트 주소
      var bp = (window.KW && KW.base) || '';
      url = location.origin + (bp && su.indexOf(bp + '/') !== 0 ? bp : '') + su;
      title = btn.getAttribute('data-share-title') || title;
    }
    url = shareUrl(url);
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
    var dock = document.querySelector('[data-rdock]'), headBar = document.querySelector('[data-report-bar]');
    var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.toc-side a'));
    var heads = tocLinks.map(function (a) { return document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1))); });
    var ticking = false;
    var pill = document.querySelector('[data-read-pill]');
    var pillPart = pill && pill.querySelector('[data-rp-part]'), pillLeft = pill && pill.querySelector('[data-rp-left]');
    var mins = parseInt(report.getAttribute('data-min') || '0', 10) || 20;
    function onScroll() {
      ticking = false;
      var rect = report.getBoundingClientRect();
      var total = rect.height - window.innerHeight;
      var p = total > 0 ? Math.min(1, Math.max(0, -rect.top / total)) : 0;
      if (bar) bar.style.width = (p * 100).toFixed(1) + '%';
      if (topBtn) topBtn.classList.toggle('show', window.scrollY > 900);
      // 읽는 중 반응 줄: 머리의 반응 줄이 화면 위로 지나가면 보인다
      if (dock) { var hb = headBar ? headBar.getBoundingClientRect().bottom : 400; dock.hidden = hb > 0; }
      var active = -1;
      for (var i = 0; i < heads.length; i++) { if (heads[i] && heads[i].getBoundingClientRect().top < 140) active = i; }
      tocLinks.forEach(function (a, i) { a.classList.toggle('active', i === active); });
      // 읽는 중 위치 알림(지금 몇 부 · 남은 시간): 1부를 지나면 보이고 끝에 가면 숨는다. 누르면 다음 부로
      if (pill) {
        var cur = active >= 0 ? tocLinks[active].textContent.trim() : '';
        var m = /^([1-6])부/.exec(cur);
        var show = !!m && p > 0.04 && p < 0.97;
        pill.hidden = !show;
        if (show) {
          var left = Math.max(1, Math.round(mins * (1 - p)));
          pillPart.textContent = m[1] + '부 / 6부';
          pillLeft.textContent = '남은 약 ' + left + '분';
          var nx = null;
          for (var k = active + 1; k < tocLinks.length; k++) { if (/^[2-6]부/.test(tocLinks[k].textContent.trim())) { nx = tocLinks[k]; break; } }
          pill.setAttribute('href', nx ? nx.getAttribute('href') : '#community');
          pill.setAttribute('aria-label', nx ? '다음: ' + nx.textContent.trim() : '이야기로');
        }
      }
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
      kwEv('yt_play');
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
    else if (a === 'bottom') window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' });
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
      var ex = document.querySelector('[data-explore]'); if (ex) ex.hidden = !!q; // 검색어가 있으면 탐색 탭을 숨기고 결과만
      if (!q) { results.innerHTML = ''; countEl.textContent = ''; return; }
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
      // 검색 결과가 4개 이상이면 3번째 뒤에 광고 하나(쿠팡 상자, 결과보다 먼저 보이지 않게)
      var exT = document.querySelector('template[data-ex-ad]');
      if (exT && hits.length >= 4) { var f0 = document.importNode(exT.content, true), bx = f0.querySelector('.ad'); results.children[2].after(f0); if (window.kwAdNew && bx) kwAdNew(bx.classList.contains('ad-coupang-products') ? bx : bx.querySelector('.ad-coupang-products')); }
      if (window.kwLogSearch) window.kwLogSearch(q, hits.length);
    }
    var timer;
    input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(run, 120); });
    // 탐색 탭(인기 종목·테마·많이 본 리포트·최근 이야기). 고른 탭은 주소(#tab=)와 이 탭 세션에 기억
    (function () {
      var tabs = document.querySelectorAll('[data-ex-tab]'); if (!tabs.length) return;
      function pick(k) {
        tabs.forEach(function (b) { b.setAttribute('aria-selected', b.getAttribute('data-ex-tab') === k ? 'true' : 'false'); });
        document.querySelectorAll('[data-ex-pane]').forEach(function (p) { p.hidden = p.getAttribute('data-ex-pane') !== k; });
        try { sessionStorage.setItem('kw-ex', k); history.replaceState(null, '', location.pathname + location.search + '#tab=' + k); } catch (e) {}
      }
      tabs.forEach(function (b) { b.addEventListener('click', function () { pick(b.getAttribute('data-ex-tab')); }); });
      // 다른 탭(테마·리포트) 목록 6번째 줄 뒤에 광고 하나씩(첫 탭은 화면에 처음부터 있는 광고)
      var exT2 = document.querySelector('template[data-ex-ad]');
      if (exT2) document.querySelectorAll('[data-ex-pane]:not([data-ex-pane="tickers"]) .ex-list').forEach(function (ul) {
        var li = ul.children[5]; if (!li || ul.children.length < 8) return;
        var holder = document.createElement('li'); holder.className = 'ex-ad'; holder.appendChild(document.importNode(exT2.content, true)); li.after(holder);
        var bx = holder.querySelector('.ad-coupang-products'); if (window.kwAdNew && bx) kwAdNew(bx);
      });
      var start = (/#tab=(\w+)/.exec(location.hash) || [])[1]; try { start = start || sessionStorage.getItem('kw-ex'); } catch (e) {}
      if (start && document.querySelector('[data-ex-pane="' + start + '"]')) pick(start);
    })();
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
  // 본문 그림(사건 막대·시기 띠)에서 접힌 상자 안 카드로 갈 때: 감싼 상자를 펼친 뒤 그 자리로
  function openTo(id) {
    var t = id && document.getElementById(id); if (!t) return false;
    for (var n = t; n; n = n.parentElement) if (n.tagName === 'DETAILS') n.open = true;
    t.scrollIntoView({ block: 'start' });
    if (t.classList) { t.classList.add('kfig-hit'); setTimeout(function () { t.classList.remove('kfig-hit'); }, 1600); }
    return true;
  }
  // 홈 → 리포트·글로 넘어간 횟수(홈 체류 시간 대신 볼 숫자, 운영 통계 '홈 → 리포트 클릭률')
  if (/^\/(index\.html)?$/.test(location.pathname.replace((window.KW && KW.base) || '', '') || '/')) document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]'); if (!a || !window.kwEv) return;
    var h = a.getAttribute('href') || '';
    if (/\/r\/[a-z0-9-]+\/|\/p\/\?r=/.test(h)) kwEv('home_report'); else if (/\/p\/\?id=/.test(h)) kwEv('home_post');
  }, true);
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('.kfig a[href^="#"]'); if (!a) return;
    var id = decodeURIComponent(a.getAttribute('href').slice(1));
    if (openTo(id)) { e.preventDefault(); try { history.replaceState(null, '', '#' + id); } catch (x) {} if (window.kwEv) kwEv('fig_click'); }
  });
  if (/^#ev-\d+$/.test(location.hash)) setTimeout(function () { openTo(location.hash.slice(1)); }, 50);
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
    // 학습용 다른 후보 묶음은 <template> 안에 있다(문서에는 보이는 묶음 하나만). 고르기 전에 꺼내 놓는다
    var alt = box.querySelector('template[data-cp-alt]');
    if (alt) { (box.querySelector('.cp-rot') || box).appendChild(document.importNode(alt.content, true)); alt.remove(); }
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
  if (!API || navigator.webdriver || /bot|crawl|spider|preview|lighthouse|headless|externalhit|meta-external|scrap/i.test(navigator.userAgent)) return;
  var LS = function (k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
  var SS = function (k, v) { try { if (v === undefined) return sessionStorage.getItem(k); sessionStorage.setItem(k, v); } catch (e) { return null; } };
  if (LS('kw-noan') === '1') return; // 운영자가 '내 방문 빼기'를 켠 기기
  var isNew = !LS('kw-did');
  // 앱(홈 화면에 설치)으로 열었는지, 운영체제·브라우저 종류(카카오톡·네이버 앱 안 브라우저 포함)
  var isApp = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
  var UA = navigator.userAgent;
  var osName = /iphone|ipad|ipod/i.test(UA) || (/macintosh/i.test(UA) && navigator.maxTouchPoints > 1) ? 'ios' : /android/i.test(UA) ? 'android' : /windows/i.test(UA) ? 'windows' : /macintosh/i.test(UA) ? 'mac' : /linux/i.test(UA) ? 'linux' : 'other';
  var brName = /kakaotalk/i.test(UA) ? 'kakaotalk' : /naver\(inapp|NAVER/.test(UA) ? 'naver' : /instagram/i.test(UA) ? 'instagram' : /FBAN|FBAV/.test(UA) ? 'facebook'
    : /Whale/.test(UA) ? 'whale' : /SamsungBrowser/.test(UA) ? 'samsung' : /Edg\//.test(UA) ? 'edge' : /Firefox|FxiOS/.test(UA) ? 'firefox' : /CriOS|Chrome/.test(UA) ? 'chrome' : /Safari/.test(UA) ? 'safari' : 'other';
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
    // 세분화 유입: 채널 > 세부 출처(네이버 검색/블로그/카페, 구글 검색/디스커버, 카톡 공유 등). 리퍼러는 도메인만 쓴다
    var fine = classify(h, UA, u);
    SS('kw-ch', fine[0]); SS('kw-sd', fine[1]); SS('kw-rh', h ? h.replace(/^www\./, '').slice(0, 80) : '');
    SS('kw-lp', location.pathname.toLowerCase());
    var qs = new URLSearchParams(location.search), utm = {};
    ['source', 'medium', 'campaign', 'content'].forEach(function (k) { var v = qs.get('utm_' + k); if (v) utm[k.charAt(0) === 'c' && k !== 'campaign' ? 't' : k.charAt(0)] = v.slice(0, 60); });
    SS('kw-utm', Object.keys(utm).length ? JSON.stringify(utm) : '');
  }
  function classify(h, ua, u) {
    if (u) { // utm_source가 있으면 그 값을 세부 출처로, 채널은 값으로 추정
      var us = u.toLowerCase().replace(/[^a-z0-9.-]/g, '').slice(0, 40) || 'utm';
      if (us === 'share') { // 사이트의 공유 버튼으로 퍼진 링크: 어느 앱에서 열었는지까지
        var app = /kakaotalk/i.test(ua) ? 'kakaotalk' : /instagram/i.test(ua) ? 'instagram' : /FBAN|FBAV/.test(ua) ? 'facebook' : /Line\//.test(ua) ? 'line' : /NAVER\(inapp|naver/i.test(ua) ? 'naver' : /threads|barcelona/i.test(ua) ? 'threads' : '';
        return ['messenger', 'share' + (app ? '-' + app : '')];
      }
      var uc = /youtube|yt/.test(us) ? 'youtube' : /naver|google|daum|bing/.test(us) ? 'search' : /kakao|telegram|line|band/.test(us) ? 'messenger'
        : /mail|newsletter|stibee/.test(us) ? 'email' : /x|twitter|threads|instagram|facebook|tiktok/.test(us) ? 'social' : 'referral';
      return [uc, us];
    }
    if (!h) { // 리퍼러 없음: 앱 안 브라우저면 그 앱에서 공유된 링크로 본다
      if (/kakaotalk/i.test(ua)) return ['messenger', 'kakaotalk'];
      if (/NAVER\(inapp|naver/i.test(ua)) return ['search', 'naver-app'];
      if (/instagram/i.test(ua)) return ['social', 'instagram'];
      if (/FBAN|FBAV/.test(ua)) return ['social', 'facebook'];
      if (/Line\//.test(ua)) return ['messenger', 'line'];
      if (/DaumApps/.test(ua)) return ['search', 'daum-app'];
      return ['direct', 'direct'];
    }
    var R = [
      [/chatgpt\.com$|openai\.com$/, 'ai', 'chatgpt'], [/perplexity\.ai$/, 'ai', 'perplexity'], [/gemini\.google\.com$/, 'ai', 'gemini'], [/claude\.ai$/, 'ai', 'claude'], [/copilot\.microsoft\.com$/, 'ai', 'copilot'],
      [/^(m\.)?search\.naver\.com$|^search\.naver\.com$/, 'search', 'naver-search'], [/^(m\.)?blog\.naver\.com$/, 'community', 'naver-blog'], [/^(m\.)?cafe\.naver\.com$|^cafe\.naver\.com$/, 'community', 'naver-cafe'],
      [/^(m\.|n\.)?news\.naver\.com$|^(m\.)?finance\.naver\.com$|^(m\.)?stock\.naver\.com$/, 'referral', 'naver-finance'], [/^(m\.)?kin\.naver\.com$/, 'community', 'naver-kin'], [/naver\.com$/, 'search', 'naver-etc'],
      [/^(www\.)?google\.[a-z.]+$/, 'search', 'google-search'], [/^news\.google\.com$/, 'referral', 'google-news'], [/googlequicksearchbox|discover\.google/, 'search', 'google-discover'], [/google\./, 'search', 'google-etc'],
      [/^(m\.)?search\.daum\.net$/, 'search', 'daum-search'], [/^(m\.)?cafe\.daum\.net$/, 'community', 'daum-cafe'], [/daum\.net$/, 'search', 'daum-etc'], [/kakao\.com$/, 'messenger', 'kakao-web'],
      [/bing\.com$/, 'search', 'bing'], [/duckduckgo\.com$/, 'search', 'duckduckgo'], [/yahoo\./, 'search', 'yahoo'], [/zum\.com$/, 'search', 'zum'],
      [/youtube\.com$|youtu\.be$/, 'youtube', 'youtube'],
      [/(^|\.)(x|twitter)\.com$|^t\.co$/, 'social', 'x'], [/threads\.(net|com)$/, 'social', 'threads'], [/instagram\.com$/, 'social', 'instagram'], [/facebook\.com$|fb\.com$/, 'social', 'facebook'],
      [/tiktok\.com$/, 'social', 'tiktok'], [/linkedin\.com$/, 'social', 'linkedin'], [/reddit\.com$/, 'community', 'reddit'], [/band\.us$/, 'messenger', 'band'], [/t\.me$|telegram/, 'messenger', 'telegram'],
      [/dcinside\.com$/, 'community', 'dcinside'], [/fmkorea\.com$/, 'community', 'fmkorea'], [/clien\.net$/, 'community', 'clien'], [/ppomppu\.co\.kr$/, 'community', 'ppomppu'],
      [/theqoo\.net$/, 'community', 'theqoo'], [/ruliweb\.com$/, 'community', 'ruliweb'], [/paxnet\.co\.kr$/, 'community', 'paxnet'], [/stocktwits\.com$/, 'community', 'stocktwits'],
      [/tistory\.com$/, 'community', 'tistory'], [/brunch\.co\.kr$/, 'community', 'brunch'], [/postype\.com$/, 'community', 'postype'], [/velog\.io$/, 'community', 'velog'],
      [/investing\.com$/, 'referral', 'investing'], [/tossinvest\.com$|toss\.im$/, 'referral', 'toss'], [/stibee\.com$|mail\./, 'email', 'email'],
      [/drkimworld\.com$/, 'internal', 'internal']
    ];
    for (var i = 0; i < R.length; i++) if (R[i][0].test(h)) return [R[i][1], R[i][2]];
    return ['referral', h.replace(/^www\./, '').replace(/^m\./, '').slice(0, 40)];
  }
  var active = 0, last = Date.now(), maxSc = 0, sent = false, human = false;
  ['scroll', 'pointerdown', 'keydown', 'touchstart', 'mousemove', 'wheel'].forEach(function (e) { addEventListener(e, function (ev) { last = Date.now(); if (ev.isTrusted && e !== 'scroll') human = true; }, { passive: true }); });
  setInterval(function () { if (document.visibilityState === 'visible' && Date.now() - last < 30000) active++; }, 1000);
  addEventListener('scroll', function () {
    var d = document.documentElement, max = d.scrollHeight - innerHeight;
    if (max > 0) maxSc = Math.max(maxSc, Math.round(Math.min(1, scrollY / max) * 100));
  }, { passive: true });
  function send() {
    if (sent) return;
    // 봇 걸러내기: 화면을 한 번도 만지지 않았고 15초도 머물지 않았으면 보내지 않는다(링크 검사·미리보기 봇은 열었다 바로 닫는다)
    if (!human && active < 15) return;
    sent = true;
    // 30초 이상 머문 세션(engaged)은 세션 누적 시간이 처음 30초를 넘는 페이지에서 한 번만 센다(페이지마다 세면 100%를 넘음)
    var acc = parseInt(SS('kw-act'), 10) || 0, en = (acc < 30 && acc + active >= 30) ? 1 : 0; SS('kw-act', String(acc + active));
    var did = LS('kw-did') || '';
    var body = JSON.stringify({ p: location.pathname, r: src, m: matchMedia('(max-width: 759px)').matches ? 1 : 0, n: isNew ? 1 : 0, s: n, a: active, en: en, sc: maxSc,
      app: isApp ? 1 : 0, hu: human ? 1 : 0, os: osName, br: brName, ev: Object.keys(window.kwEvents || {}),
      ch: SS('kw-ch') || 'direct', sd: SS('kw-sd') || src, rh: n === 1 ? (SS('kw-rh') || '') : '', lp: SS('kw-lp') || location.pathname, u: (function () { try { return JSON.parse(SS('kw-utm') || 'null'); } catch (e) { return null; } })() });
    var url = API + '/v1/hit' + (/^[A-Za-z0-9_-]{22,64}$/.test(did) ? '?d=' + did : '');
    try { if (navigator.sendBeacon && navigator.sendBeacon(url, body)) return; } catch (e) {}
    try { fetch(url, { method: 'POST', body: body, keepalive: true, credentials: 'include' }); } catch (e) {}
  }
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') send(); });
  addEventListener('pagehide', send);
})();

// ---------- 웹앱: 서비스 워커 등록 + '홈 화면에 설치' ----------
// 설치 경로(모두 '설치 가능할 때만' 보인다):
//  · 머리줄 '앱 설치' 버튼(모든 페이지, 늘 같은 자리) · 바닥글 링크
//  · 아래 안내 줄: 두 번째 페이지부터, 읽기 시작(스크롤 25% 또는 15초) 뒤 한 번. 세션당 한 번, 닫으면 7일 쉼. 화면을 밀지 않는 떠 있는 줄
//  · 리포트 끝 카드(본문 바로 뒤) · 홈 피드 카드(휴대폰). 카드는 닫으면 14일 쉼
// 안드로이드·PC 크롬은 설치 창을 바로 띄운다. 아이폰은 '공유 → 홈 화면에 추가' 안내 창.
// 카카오톡·네이버·인스타그램 등 앱 안 브라우저는 설치가 안 되므로 크롬(아이폰은 사파리 안내)으로 열어 준다(?kwapp=1 → 열리면 바로 안내 줄).
(function () {
  var base = (window.KW && KW.base) || '';
  if ('serviceWorker' in navigator && location.protocol === 'https:') {
    addEventListener('load', function () { navigator.serviceWorker.register(base + '/sw.js').catch(function () {}); });
  }
  var standalone = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
  if (standalone) { document.documentElement.classList.add('is-app'); return; }
  if (navigator.webdriver && !/kwtest/.test(location.hash)) return;
  var ua = navigator.userAgent, ios = /iphone|ipad|ipod/i.test(ua) || (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
  var android = /android/i.test(ua), kakao = /kakaotalk/i.test(ua);
  var inapp = kakao || /NAVER\(inapp|naver|instagram|FBAN|FBAV|FB_IAB|Line\/|DaumApps|everytimeApp|; wv\)/i.test(ua);
  var iosSafari = ios && !inapp && /safari/i.test(ua) && !/crios|fxios|edgios/i.test(ua);
  var iosOther = ios && !inapp && !iosSafari;
  var samsung = android && !inapp && /SamsungBrowser/.test(ua);
  var mq = function (q) { return !!(window.matchMedia && matchMedia(q).matches); };
  var LS = function (k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
  var SS = function (k, v) { try { if (v === undefined) return sessionStorage.getItem(k); sessionStorage.setItem(k, v); } catch (e) { return null; } };
  var deferred = null, done = false;
  function mode() {
    if (done) return '';
    if (deferred) return 'prompt';
    if (inapp) return (android || kakao) ? 'escape' : 'inapp-ios';
    if (iosSafari) return 'ios';
    if (iosOther) return 'ios-other';
    if (samsung) return 'menu';
    return '';
  }
  function toast(t, ms) { var x = document.querySelector('.toast'); if (!x) return; x.textContent = t; x.classList.add('show'); setTimeout(function () { x.classList.remove('show'); }, ms || 2200); }
  function iosHelp() { return '사파리 아래쪽 공유 버튼(네모에 위 화살표)을 누른 뒤 "홈 화면에 추가"를 고르세요.'; }
  function snoozed(k, days) { return Date.now() - (+LS(k) || 0) < days * 864e5; }
  var label = function () { var m = mode(); return m === 'escape' ? '크롬에서 열기' : (m === 'ios' || m === 'ios-other' || m === 'inapp-ios' || m === 'menu') ? '방법 보기' : '설치'; };
  if (kakao && !android) label = function () { return '사파리에서 열기'; };

  function openOutside() {
    var u = location.href.replace(/#.*$/, ''); u += (u.indexOf('?') < 0 ? '?' : '&') + 'kwapp=1';
    if (kakao) { location.href = 'kakaotalk://web/openExternal?url=' + encodeURIComponent(u); return; }
    location.href = 'intent://' + u.replace(/^https?:\/\//, '') + '#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=' + encodeURIComponent(u) + ';end';
  }
  var sheet = null;
  function guide(m) { // 설치 창을 띄울 수 없는 브라우저: 따라 하기 안내 창
    if (!sheet) {
      sheet = document.createElement('dialog'); sheet.className = 'kw-dlg install-sheet';
      sheet.addEventListener('click', function (e) { if (e.target === sheet) sheet.close(); });
      document.body.appendChild(sheet);
    }
    var steps = m === 'ios' ? ['아래쪽(또는 주소창 옆) <b>공유 버튼</b>을 누르세요. 네모에 위 화살표 모양이에요. 안 보이면 <b>⋯</b> 안에 있어요.', '목록을 올려 <b>홈 화면에 추가</b>를 고르세요.', '오른쪽 위 <b>추가</b>를 누르면 끝이에요.']
      : m === 'ios-other' ? ['주소창 옆 <b>공유 버튼</b>(네모에 위 화살표)을 누르세요.', '<b>홈 화면에 추가</b>를 고르세요.', '<b>추가</b>를 누르면 끝이에요. 메뉴에 없으면 사파리에서 열어 주세요.']
      : m === 'inapp-ios' ? ['이 화면은 앱 안 브라우저라 설치가 안 돼요.', '오른쪽 아래(또는 위) <b>⋯</b> 메뉴에서 <b>Safari로 열기</b>를 누르세요.', '사파리에서 머리줄의 <b>앱 설치</b>를 다시 누르세요.']
      : ['브라우저 메뉴(<b>≡</b> 또는 <b>⋮</b>)를 여세요.', '<b>현재 페이지 추가</b> → <b>홈 화면</b>, 또는 <b>홈 화면에 추가</b>를 고르세요.', '바탕화면의 김박사 월드 아이콘으로 열면 돼요.'];
    sheet.innerHTML = '<div class="kw-dlg-head"><h2>홈 화면에 김박사 월드 추가</h2><button type="button" class="kw-dlg-x" aria-label="닫기">×</button></div>'
      + '<div class="kw-dlg-body"><div class="is-hero"><img src="' + base + '/static/icon-192.png" alt="" width="52" height="52"><p>앱스토어 없이 <b>무료</b>로, 저장공간도 거의 안 써요. 홈 화면 아이콘으로 바로 열리고 주소창 없이 넓게 보여요.</p></div>'
      + '<ol class="is-steps">' + steps.map(function (t) { return '<li>' + t + '</li>'; }).join('') + '</ol>'
      + '<button type="button" class="btn btn-primary" data-is-ok>알겠어요</button></div>';
    sheet.querySelector('.kw-dlg-x').onclick = sheet.querySelector('[data-is-ok]').onclick = function () { sheet.close(); };
    if (sheet.showModal) { if (!sheet.open) sheet.showModal(); } else toast(iosHelp(), 6000);
  }
  window.kwCanInstall = function () { return !!mode(); };
  window.kwInstall = function (src) {
    kwEv('install_click'); if (src) kwEv('ic_' + src);
    var m = mode();
    if (m === 'prompt') {
      var d = deferred; deferred = null;
      d.prompt();
      d.userChoice.then(function (c) { if (c && c.outcome === 'accepted') { kwEv('install_accept'); done = true; toast('홈 화면에 추가했습니다'); hideAll(); } else { kwEv('install_dismiss'); refresh(); } }).catch(function () {});
      return;
    }
    if (m === 'escape') {
      kwEv('install_inapp');
      if (kakao || android) { openOutside(); return; }
    }
    if (m === 'ios' || m === 'ios-other' || m === 'inapp-ios') kwEv('ios_help');
    guide(m || 'menu');
  };
  function hideAll() {
    document.querySelectorAll('[data-install]').forEach(function (n) { n.hidden = true; });
    document.querySelectorAll('.install-card, .install-bar').forEach(function (n) { n.remove(); });
  }
  function refresh() { // 설치 가능 여부가 바뀔 때마다(설치 창 거절 뒤엔 크롬이 다시 허용할 때까지 숨김)
    var on = !!mode();
    document.querySelectorAll('[data-install]').forEach(function (n) { n.hidden = !on; });
    if (window.kwFitHeader) kwFitHeader();
    if (on) { feedCard(); reportCard(); armBar(); }
  }
  document.addEventListener('click', function (e) { var b = e.target.closest && e.target.closest('[data-install]'); if (b) { e.preventDefault(); window.kwInstall(b.getAttribute('data-src') || ''); } });
  addEventListener('appinstalled', function () { kwEv('installed'); done = true; hideAll(); });

  // 카드(피드·리포트 끝): 본문 흐름 안, 닫으면 14일
  function makeCard(src, title, sub) {
    var w = document.createElement('div'); w.className = 'card install-card'; w.setAttribute('data-src', src);
    w.innerHTML = '<img src="' + base + '/static/icon-192.png" alt="" width="44" height="44"><div class="ic-txt"><strong></strong><span></span></div>'
      + '<div class="ic-row"><button type="button" class="btn btn-primary" data-install-go></button><button type="button" class="btn" data-install-x>닫기</button></div>';
    w.querySelector('strong').textContent = title; w.querySelector('.ic-txt span').textContent = sub; w.querySelector('[data-install-go]').textContent = label();
    w.querySelector('[data-install-go]').addEventListener('click', function () { window.kwInstall(src); });
    w.querySelector('[data-install-x]').addEventListener('click', function () { LS('kw-install-x', String(Date.now())); document.querySelectorAll('.install-card').forEach(function (n) { n.remove(); }); });
    return w;
  }
  function feedCard() { // 홈 피드 두 번째 글 뒤(휴대폰)
    var list = document.querySelector('.feed-list');
    if (!list || list.querySelector('.install-card') || snoozed('kw-install-x', 14) || !mq('(max-width: 759px)')) return;
    var after = list.querySelectorAll(':scope > article.post')[1]; if (!after) return;
    after.after(makeCard('feed', '김박사 월드를 앱처럼', '홈 화면에 추가하면 한 번에 열리고, 화면도 더 넓게 보여요.')); kwEv('install_card');
  }
  function reportCard() { // 리포트 본문을 다 읽은 자리(출처 바로 위). 다 읽은 독자가 가장 잘 설치한다
    var prose = document.querySelector('article.report > .prose');
    if (!prose || document.querySelector('.install-card') || snoozed('kw-install-x', 14)) return;
    var c = makeCard('report', '다음 리포트도 한 번에 보기', '홈 화면에 김박사 월드를 추가하세요. 무료이고, 아이콘 한 번으로 바로 열려요.');
    c.classList.add('install-card-report'); prose.after(c);
    if (window.IntersectionObserver) { var io = new IntersectionObserver(function (es) { if (es[0].isIntersecting) { kwEv('install_card'); io.disconnect(); } }); io.observe(c); }
  }

  // 아래 안내 줄: 떠 있는 줄(본문을 밀지 않음), 세션당 한 번, 닫으면 7일
  var pv = (+LS('kw-pv') || 0) + 1; LS('kw-pv', String(pv));
  var fromEscape = /[?&]kwapp=1/.test(location.search);
  if (fromEscape && history.replaceState) { try { history.replaceState(null, '', location.pathname + location.search.replace(/([?&])kwapp=1&?/, '$1').replace(/[?&]$/, '') + location.hash); } catch (e) {} }
  var armed = false;
  function armBar() {
    if (armed || !mq('(max-width: 759px)')) return;
    if (!fromEscape && (pv < 2 || SS('kw-ib') || snoozed('kw-install-b', 7))) return;
    armed = true;
    var shown = false, t0 = Date.now();
    function show() {
      if (shown || !mode()) return; shown = true; SS('kw-ib', '1');
      removeEventListener('scroll', onScroll); clearTimeout(tm);
      var b = document.createElement('div'); b.className = 'install-bar'; b.setAttribute('role', 'region'); b.setAttribute('aria-label', '앱 설치 안내');
      b.innerHTML = '<img src="' + base + '/static/icon-192.png" alt="" width="36" height="36"><div class="ib-txt"><strong>김박사 월드 앱</strong><span>무료 · 홈 화면에서 한 번에 열기</span></div>'
        + '<button type="button" class="btn btn-primary btn-small" data-ib-go></button><button type="button" class="ib-x" aria-label="닫기">×</button>';
      b.querySelector('[data-ib-go]').textContent = label();
      b.querySelector('[data-ib-go]').addEventListener('click', function () { window.kwInstall('bar'); });
      b.querySelector('.ib-x').addEventListener('click', function () { LS('kw-install-b', String(Date.now())); b.classList.remove('on'); setTimeout(function () { b.remove(); }, 250); });
      document.body.appendChild(b); requestAnimationFrame(function () { requestAnimationFrame(function () { b.classList.add('on'); }); });
      kwEv('install_bar');
    }
    function onScroll() {
      var d = document.documentElement, max = d.scrollHeight - innerHeight;
      if (max > 0 && scrollY / max >= 0.25) show();
    }
    var tm = setTimeout(show, fromEscape ? 600 : 15000);
    addEventListener('scroll', onScroll, { passive: true });
  }

  addEventListener('beforeinstallprompt', function (e) { e.preventDefault(); deferred = e; kwEv('install_prompt'); refresh(); });
  if (mode()) { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', refresh); else refresh(); }
})();

// 쿠팡 다이내믹 배너(가로 고정 크기)를 좁은 화면에서 비율대로 줄인다
(function () {
  var boxes = document.querySelectorAll('.cp-banner'); if (!boxes.length) return;
  function fit() {
    boxes.forEach(function (b) {
      var w = +b.getAttribute('data-w') || 680, inner = b.querySelector('.cp-banner-in'); if (!inner) return;
      var s = Math.min(1, b.clientWidth / w);
      inner.style.transform = s < 1 ? 'scale(' + s + ')' : '';
    });
  }
  fit(); addEventListener('resize', fit); addEventListener('load', fit);
})();

// 유튜브에서 온 독자에게만: 리포트 위쪽에 "영상에서 다 못 다룬 내용" 바로가기 줄
(function () {
  var nav = document.querySelector('[data-yt-jump]'); if (!nav) return;
  var src = ''; try { src = sessionStorage.getItem('kw-src') || ''; } catch (e) {}
  var ref = ''; try { ref = document.referrer ? new URL(document.referrer).hostname : ''; } catch (e) {}
  var utm = (new URLSearchParams(location.search).get('utm_source') || '').toLowerCase();
  if (src === 'youtube' || /youtube\.com$|youtu\.be$/.test(ref) || utm === 'youtube') { nav.hidden = false; if (window.kwEv) kwEv('yt_jump_shown'); }
  nav.addEventListener('click', function (e) { if (e.target.closest('a') && window.kwEv) kwEv('yt_jump_click'); });
})();

// 본문 중간 '함께 읽기' 링크 누름(2026-10-16: 리포트 → 다음 리포트 이동 측정)
(function () {
  var a = document.querySelector('[data-mid-next]'); if (!a) return;
  a.addEventListener('click', function () { if (window.kwEv) kwEv('mid_next_click'); });
})();

// 광고·제휴 문의 메일: 화면에는 '＠'로 적어 두고(주소 수집 로봇 막기), 누르면 진짜 주소로 메일을 연다
document.addEventListener('click', function (e) {
  var a = e.target.closest && e.target.closest('a.mail-link'); if (!a) return;
  e.preventDefault();
  location.href = 'mailto:' + a.getAttribute('data-u') + '@' + a.getAttribute('data-d') + '?subject=' + encodeURIComponent('[김박사 월드 광고·제휴 문의]');
});
