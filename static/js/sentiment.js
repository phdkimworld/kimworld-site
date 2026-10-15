// 종목 투자 심리 투표(종목 화면 위): 하루 한 표 → 오늘 비율·30일 누적 심리 지수·추이 그래프
// 30일 누적 지수 = 최근 30일 '오를 것 같다' 표 ÷ 전체 표 × 100 (50 위 강세, 아래 약세). 색은 한국 시장 관례(상승 빨강·하락 파랑)
document.addEventListener('DOMContentLoaded', function () {
  'use strict';
  var box = document.querySelector('[data-sent]'); if (!box || !window.KWC) return;
  var C = window.KWC, tk = box.getAttribute('data-ticker');
  var q = function (s) { return box.querySelector(s); }, qa = function (s) { return Array.prototype.slice.call(box.querySelectorAll(s)); };
  var DATA = null, DAYS = 30, busy = false;
  var NS = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); return e; }
  function pct(b, r) { return b + r ? Math.round(b / (b + r) * 100) : null; }
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
      tease.textContent = d.n30 ? '투표하면 30일 투자 심리 지수와 추이 그래프가 열립니다' : '첫 표를 던지고 30일 투자 심리 지수를 시작해 보세요';
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

  function load() { return C.api('/v1/sentiment/' + encodeURIComponent(tk)).then(paint).catch(function () {}); }
  qa('[data-sent-v]').forEach(function (b) {
    b.addEventListener('click', function () {
      var v = b.getAttribute('data-sent-v');
      if (busy || (DATA && DATA.voted === v)) return;
      busy = true; box.classList.add('is-busy');
      var first = !(DATA && DATA.voted);
      C.api('/v1/sentiment/' + encodeURIComponent(tk), { method: 'POST', body: { v: v } }).then(function (d) {
        busy = false; box.classList.remove('is-busy');
        if (d && d.voted) { paint(d); if (window.kwEv) kwEv('sent_vote'); C.flash(first ? '투표했어요. 내일 또 참여해 주세요' : '오늘 표를 바꿨어요'); }
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
  load();
});
