// 종목 투자 심리 투표(종목 화면 위): 하루 한 표 → 오늘 비율·30일 누적 심리 지수·추이 그래프
// 30일 누적 지수 = 최근 30일 '오를 것 같다' 표 ÷ 전체 표 × 100 (50 위 강세, 아래 약세). 색은 한국 시장 관례(상승 빨강·하락 파랑)
document.addEventListener('DOMContentLoaded', function () {
  'use strict';
  var C = window.KWC; if (!C) return;
  var box = document.querySelector('[data-sent]'), tk = box ? box.getAttribute('data-ticker') : '';
  var bigLoad = null;
  function pct(b, r) { return b + r ? Math.round(b / (b + r) * 100) : null; }
  if (box) (function () {
  var q = function (s) { return box.querySelector(s); }, qa = function (s) { return Array.prototype.slice.call(box.querySelectorAll(s)); };
  var DATA = null, DAYS = 30, busy = false;
  var NS = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); return e; }
  function kday(off) { return new Date(Date.now() + 9 * 3600e3 - off * 864e5).toISOString().slice(0, 10); }
  function label(p) { return p == null ? '' : p >= 60 ? '강세 우위' : p > 52 ? '조금 강세' : p >= 48 ? '팽팽' : p > 40 ? '조금 약세' : '약세 우위'; }

  function paint(d) {
    DATA = d;
    var voted = d.voted;
    qa('[data-sent-v]').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-sent-v') === voted ? 'true' : 'false'); });
    box.classList.toggle('is-voted', !!voted);
    var meta = q('[data-sent-meta]'), tease = q('[data-sent-tease]');
    if (!voted) {
      meta.textContent = d.n30 ? '지난 30일 ' + C.num(d.n30) + '표' : '';
      tease.textContent = d.n30 ? '투표하면 다른 투자자 ' + C.num(d.n30) + '표의 결과(강세·약세 비율)와 30일 추이 그래프가 열려요' : '투표하면 결과가 열려요. 첫 표의 주인공이 되어 보세요';
      tease.hidden = false; q('[data-sent-res]').hidden = true;
      qa('[data-sent-pct]').forEach(function (e) { e.textContent = ''; });
      return;
    }
    tease.hidden = true; q('[data-sent-res]').hidden = false;
    var t = d.today, p30 = pct(d.d30.bull, d.d30.bear), pt = pct(t.bull, t.bear);
    meta.textContent = (d.streak > 1 ? d.streak + '일 연속 참여 · ' : '') + '내일 다시 투표할 수 있어요';
    // 버튼에는 30일 누적 비율(오늘 몇 표만으로 100%가 되는 착시를 피한다)
    q('[data-sent-pct="bull"]').textContent = p30 == null ? '' : p30 + '%';
    q('[data-sent-pct="bear"]').textContent = p30 == null ? '' : (100 - p30) + '%';
    var idx = q('[data-sent-idx]'); idx.textContent = p30 == null ? '–' : p30;
    idx.className = 'sent-n ' + (p30 == null ? '' : p30 >= 50 ? 'up' : 'down');
    q('[data-sent-lab]').textContent = label(p30) + ' · ' + C.num(d.d30.bull + d.d30.bear) + '표';
    var td = q('[data-sent-today]'); td.textContent = '';
    var up = document.createElement('span'); up.className = 't-up'; up.textContent = '▲ ' + C.num(t.bull);
    var dn = document.createElement('span'); dn.className = 't-down'; dn.textContent = '▼ ' + C.num(t.bear);
    td.appendChild(up); td.appendChild(document.createTextNode(' · ')); td.appendChild(dn);
    if (pt != null && t.bull + t.bear >= 10) td.appendChild(document.createTextNode(' (' + pt + '%)'));
    q('[data-sent-barb]').style.width = (p30 == null ? 50 : p30) + '%';
    q('[data-sent-barr]').style.width = (p30 == null ? 50 : 100 - p30) + '%';
    q('[data-sent-note]').textContent = '참여한 독자의 의견을 모은 것이며, 실제 주가나 매매 판단과는 다를 수 있습니다. 한 사람이 하루 한 표, 그날 안에는 바꿀 수 있어요.';
    chart();
  }

  // 그래프: 그날 강세 비율(점, 표가 많을수록 진하게) + 30일 누적 지수(선). 가운데 50 점선
  function chart() {
    var el = q('[data-sent-chart]'); el.textContent = '';
    var by = {}; (DATA.series || []).forEach(function (x) { by[x.day] = x; });
    var N = DAYS, W = 320, H = 150, L = 26, R = 8, T = 10, B = 22, iw = W - L - R, ih = H - T - B;
    var pts = [], dots = [], maxV = 1;
    for (var i = N - 1; i >= 0; i--) {
      var day = kday(i), b = 0, r = 0;
      for (var k = 0; k < 30; k++) { var x = by[kday(i + k)]; if (x) { b += x.bull; r += x.bear; } }
      var x0 = L + (N - 1 - i) / Math.max(1, N - 1) * iw;
      if (b + r) pts.push([x0, T + ih * (1 - b / (b + r))]);
      var dd = by[day]; if (dd && dd.bull + dd.bear) { dots.push([x0, T + ih * (1 - dd.bull / (dd.bull + dd.bear)), dd.bull + dd.bear]); maxV = Math.max(maxV, dd.bull + dd.bear); }
    }
    var s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': tk + ' 투자 심리 추이(최근 ' + N + '일)' });
    // 강세(위)·약세(아래) 바탕
    s.appendChild(svg('rect', { x: L, y: T, width: iw, height: ih / 2, class: 'sc-up' }));
    s.appendChild(svg('rect', { x: L, y: T + ih / 2, width: iw, height: ih / 2, class: 'sc-down' }));
    [0, 50, 100].forEach(function (v) {
      var y = T + ih * (1 - v / 100);
      s.appendChild(svg('line', { x1: L, x2: L + iw, y1: y, y2: y, class: v === 50 ? 'sc-mid' : 'sc-grid' }));
      var t = svg('text', { x: L - 5, y: y + 3.5, class: 'sc-ax', 'text-anchor': 'end' }); t.textContent = v; s.appendChild(t);
    });
    var f = function (d) { return d.slice(5).replace('-', '.'); };
    var t1 = svg('text', { x: L, y: H - 6, class: 'sc-ax' }); t1.textContent = f(kday(N - 1)); s.appendChild(t1);
    var t2 = svg('text', { x: L + iw, y: H - 6, class: 'sc-ax', 'text-anchor': 'end' }); t2.textContent = '오늘'; s.appendChild(t2);
    dots.forEach(function (d) { s.appendChild(svg('circle', { cx: d[0].toFixed(1), cy: d[1].toFixed(1), r: 2.2, class: 'sc-dot', 'fill-opacity': (0.25 + 0.6 * d[2] / maxV).toFixed(2) })); });
    if (pts.length > 1) s.appendChild(svg('polyline', { points: pts.map(function (p) { return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' '), class: 'sc-line' }));
    if (pts.length) { var lp = pts[pts.length - 1]; s.appendChild(svg('circle', { cx: lp[0].toFixed(1), cy: lp[1].toFixed(1), r: 3.6, class: 'sc-last' })); }
    el.appendChild(s);
    if (pts.length < 3) { var n = document.createElement('p'); n.className = 'sent-few'; n.textContent = '아직 기록이 쌓이는 중입니다. 매일 투표가 모이면 선이 이어져요.'; el.appendChild(n); }
  }

  function load() { return C.api('/v1/sentiment/' + encodeURIComponent(tk)).then(function (d) { paint(d); if (d && d.rp && C.paintRepost) C.paintRepost('v', tk, d.rp.n, d.rp.on); }).catch(function () {}); }
  // 투표 상자만 공유: 미리보기(카카오톡·쓰레드·X)에는 질문이, 누르면 이 종목 화면의 투표 상자로
  var shb = q('[data-sent-share]');
  if (shb) shb.addEventListener('click', function () {
    var h = q('.sent-q'), u = (C.apiBase || '') + '/s/v/' + encodeURIComponent(tk);
    var text = (h ? h.textContent.trim() : '$' + tk + ' 앞으로 어떻게 보세요?') + '\n오를까, 내릴까? 투표하고 다른 투자자들의 생각을 확인해 보세요.';
    if (window.kwEv) kwEv('poll_share');
    if (window.kwShare) return kwShare({ title: '$' + tk + ' 투자 심리 투표', text: text, url: u });
    if (navigator.share) { navigator.share({ title: '$' + tk + ' 투자 심리 투표', text: text, url: u }).catch(function () {}); return; }
    var all = text + '\n' + u;
    (navigator.clipboard ? navigator.clipboard.writeText(all) : Promise.reject()).then(function () { C.flash('투표 링크를 복사했습니다. 카카오톡·커뮤니티에 붙여 넣으세요'); }, function () { prompt('아래 내용을 복사하세요', all); });
  });
  qa('[data-sent-v]').forEach(function (b) {
    b.addEventListener('click', function () {
      var v = b.getAttribute('data-sent-v');
      if (busy || (DATA && DATA.voted === v)) return;
      busy = true; box.classList.add('is-busy');
      var first = !(DATA && DATA.voted);
      C.api('/v1/sentiment/' + encodeURIComponent(tk), { method: 'POST', body: { v: v } }).then(function (d) {
        busy = false; box.classList.remove('is-busy');
        if (d && d.voted) { paint(d); syncPolls(tk, { voted: d.voted, n30: d.d30.bull + d.d30.bear, d30: d.d30 }); if (window.kwEv) kwEv('sent_vote'); C.flash(first ? '투표했어요. 내일 또 참여해 주세요' : '오늘 표를 바꿨어요'); }
        else C.flash((d && d.message) || '투표하지 못했습니다');
      }).catch(function () { busy = false; box.classList.remove('is-busy'); C.flash('투표하지 못했습니다'); });
    });
  });
  qa('[data-sent-days]').forEach(function (b) {
    b.addEventListener('click', function () {
      DAYS = parseInt(b.getAttribute('data-sent-days'), 10);
      qa('[data-sent-days]').forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
      if (DATA && DATA.voted) chart();
    });
  });
  load(); bigLoad = load;
  })();

  // ---------- 피드 카드의 작은 투표(리포트 카드 [data-fpoll]) ----------
  // 같은 종목 카드가 여러 장이면 함께 바뀐다. 종목 화면·리포트처럼 큰 투표 상자가 있는 종목은 카드 투표를 숨긴다(중복)
  var ST = {}, fpBusy = {};
  function syncPolls(t, st) {
    ST[t] = st;
    Array.prototype.forEach.call(document.querySelectorAll('[data-fpoll][data-ticker="' + t + '"]'), function (fp) { paintPoll(fp, st); });
  }
  function paintPoll(fp, st) {
    if (tk && fp.getAttribute('data-ticker') === tk && !fp.hasAttribute('data-keep')) { fp.hidden = true; return; }
    fp.hidden = false;
    var v = st && st.voted;
    fp.classList.toggle('is-voted', !!v);
    Array.prototype.forEach.call(fp.querySelectorAll('[data-fp-v]'), function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-fp-v') === v ? 'true' : 'false'); });
    var res = fp.querySelector('[data-fp-res]'), tz = fp.querySelector('[data-fp-tease]');
    if (tz) {
      tz.hidden = !!v;
      if (!v) tz.textContent = st && st.n30 ? '🔒 투표하면 결과가 보여요 · 지난 30일 ' + C.num(st.n30) + '표' : '🔒 투표하면 다른 투자자들의 결과가 보여요';
    }
    if (!v) { res.hidden = true; return; }
    var p = pct(st.d30.bull, st.d30.bear); if (p == null) p = 50;
    res.hidden = false;
    fp.querySelector('[data-fp-bb]').style.width = p + '%'; fp.querySelector('[data-fp-br]').style.width = (100 - p) + '%';
    fp.querySelector('[data-fp-up]').textContent = '▲ 강세 ' + p + '%';
    fp.querySelector('[data-fp-down]').textContent = '약세 ' + (100 - p) + '% ▼';
    fp.querySelector('[data-fp-meta]').textContent = '30일 ' + C.num(st.n30) + '표';
  }
  var pollT = 0;
  function polls(root) {
    var fps = Array.prototype.slice.call((root || document).querySelectorAll('[data-fpoll]'));
    var need = [];
    fps.forEach(function (fp) {
      var t = fp.getAttribute('data-ticker');
      if (ST[t]) paintPoll(fp, ST[t]); else if (need.indexOf(t) < 0) need.push(t);
    });
    for (var i = 0; i < need.length; i += 40) (function (part) {
      C.api('/v1/sentiment?t=' + encodeURIComponent(part.join(','))).then(function (d) {
        part.forEach(function (t) { if (d.items && d.items[t]) syncPolls(t, d.items[t]); });
      }).catch(function () {});
    })(need.slice(i, i + 40));
  }
  window.kwPolls = function (root) { clearTimeout(pollT); pollT = setTimeout(function () { polls(root); }, 30); };
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-fp-v]'); if (!b) return;
    e.preventDefault(); e.stopPropagation();
    var fp = b.closest('[data-fpoll]'), t = fp.getAttribute('data-ticker'), v = b.getAttribute('data-fp-v');
    if (fpBusy[t] || (ST[t] && ST[t].voted === v)) return;
    fpBusy[t] = 1; fp.classList.add('is-busy');
    var first = !(ST[t] && ST[t].voted);
    C.api('/v1/sentiment/' + encodeURIComponent(t), { method: 'POST', body: { v: v } }).then(function (d) {
      fpBusy[t] = 0; fp.classList.remove('is-busy');
      if (d && d.voted) {
        syncPolls(t, { voted: d.voted, n30: d.d30.bull + d.d30.bear, d30: d.d30 });
        if (window.kwEv) { kwEv('sent_vote'); kwEv('sent_vote_feed'); }
        C.flash(first ? '투표했어요. 내일 또 참여해 주세요' : '오늘 표를 바꿨어요');
      } else C.flash((d && d.message) || '투표하지 못했습니다');
    }).catch(function () { fpBusy[t] = 0; fp.classList.remove('is-busy'); C.flash('투표하지 못했습니다'); });
  }, true);
  polls(document);
  // ---------- 리포트 업데이트 요청(종목 화면·리포트·글 화면) ----------
  function initUr(ur) {
    if (!ur || ur._kwUr) return; ur._kwUr = 1;
    var t = ur.getAttribute('data-ticker'), btn = ur.querySelector('[data-ur-btn]'), nEl = ur.querySelector('[data-ur-n]'), busy = 0;
    function paintUr(d) {
      if (!d || d.n == null) return;
      document.querySelectorAll('[data-upd-req][data-ticker="' + t + '"]').forEach(function (box) {
        box.hidden = false;
        var b = box.querySelector('[data-ur-btn]'), ne = box.querySelector('[data-ur-n]');
        b.setAttribute('aria-pressed', d.mine ? 'true' : 'false');
        b.textContent = d.mine ? '✓ 요청함 (취소하려면 누르기)' : '🔔 업데이트 요청';
        ne.textContent = d.n ? '최근 30일 ' + C.num(d.n) + '명이 새 리포트를 요청했어요' : '새 리포트가 필요하면 첫 요청을 남겨 주세요';
      });
    }
    C.api('/v1/requests/' + encodeURIComponent(t)).then(paintUr).catch(function () {});
    btn.addEventListener('click', function () {
      if (busy) return; busy = 1; btn.disabled = true;
      C.api('/v1/requests/' + encodeURIComponent(t), { method: 'POST', body: {} }).then(function (d) {
        busy = 0; btn.disabled = false;
        if (d && d.n != null) { paintUr(d); if (d.changed === 'on') { if (window.kwEv) kwEv('update_request'); C.flash('요청했어요. 요청이 많은 종목은 새 리포트 제작 순서에 반영됩니다'); } else C.flash('요청을 취소했어요'); }
        else C.flash((d && d.message) || '요청하지 못했습니다');
      }).catch(function () { busy = 0; btn.disabled = false; C.flash('요청하지 못했습니다'); });
    });
  }
  document.querySelectorAll('[data-upd-req]').forEach(initUr);
  // 글 화면처럼 나중에 그려지는 곳에서 쓰는 상자 만들기: kwUpdReq('RGTI', '최신 리포트 2026년 10월 13일 기준')
  window.kwUpdReq = function (t, head) {
    var box = document.createElement('section'); box.className = 'upd-req'; box.hidden = true;
    box.setAttribute('data-upd-req', ''); box.setAttribute('data-ticker', String(t).toUpperCase()); box.setAttribute('aria-label', '리포트 업데이트 요청');
    var tx = document.createElement('div'); tx.className = 'ur-txt';
    var st = document.createElement('strong'); st.textContent = head || ('$' + String(t).toUpperCase() + ' 새 리포트 요청'); tx.appendChild(st);
    var n = document.createElement('span'); n.className = 'muted'; n.setAttribute('data-ur-n', ''); n.textContent = '새 리포트가 필요하면 요청해 주세요'; tx.appendChild(n);
    var b = document.createElement('button'); b.type = 'button'; b.className = 'btn ur-btn'; b.setAttribute('data-ur-btn', ''); b.setAttribute('aria-pressed', 'false'); b.textContent = '🔔 업데이트 요청';
    box.appendChild(tx); box.appendChild(b);
    setTimeout(function () { initUr(box); }, 0);
    return box;
  };
  // 피드에 카드가 새로 붙으면(더 보기·대표 글 복제) 그 카드의 투표도 칠한다
  var feed = document.querySelector('[data-feed]') || document.querySelector('main');
  if (feed && window.MutationObserver) new MutationObserver(function (ms) {
    for (var i = 0; i < ms.length; i++) for (var j = 0; j < ms[i].addedNodes.length; j++) {
      var n = ms[i].addedNodes[j];
      if (n.nodeType === 1 && (n.matches('[data-fpoll]') || n.querySelector('[data-fpoll]'))) { window.kwPolls(document); if (C.topics) C.topics(document); return; }
    }
  }).observe(feed, { childList: true, subtree: true });
});
