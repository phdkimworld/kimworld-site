/* 리포트 그림 웹 애니메이션(운영자 지시 2026-11-16 ET "애니메이션을 리포트에서 렌더링 되게", 사이트 AGENTS.md '이야기형 그림').
   점진적 향상: 원고의 정지 이미지(<img>, WebP)가 기본이다. 이 파일은 그 그림의 명세(/static/figs/<slug>-<n>.json, 미디어 저장소
   tools/figkit/make.py 가 정지 이미지와 함께 만든 것)의 web 그리기 목록을 SVG로 그리고, 그림이 화면에 들어올 때 한 번만 움직인다.
   - 숫자·글자는 명세에 있는 것만 그린다(정지 이미지와 같은 좌표·같은 글자). 반복 재생 없음.
   - prefers-reduced-motion 이거나 IntersectionObserver·fetch 가 없으면 아무것도 하지 않는다(정지 이미지 그대로).
   - GSAP(자체 호스팅)는 첫 그림이 가까워질 때만 받는다. 실패하면 정지 이미지 그대로. */
(function () {
  'use strict';
  var figs = document.querySelectorAll('figure[data-fig]');
  var me = document.currentScript;
  if (!figs.length || !('IntersectionObserver' in window) || !window.fetch || !window.SVGElement) return;
  if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var GSAP = (me && me.getAttribute('data-gsap')) || '';
  var NS = 'http://www.w3.org/2000/svg';
  var gsapP = null;
  function loadGsap() {
    if (window.gsap) return Promise.resolve();
    if (!gsapP) gsapP = new Promise(function (ok, no) {
      var s = document.createElement('script'); s.src = GSAP; s.async = true; s.onload = ok; s.onerror = no; document.head.appendChild(s);
    });
    return gsapP;
  }
  function el(tag, a, parent, txt) {
    var e = document.createElementNS(NS, tag);
    for (var k in a) if (a[k] !== undefined && a[k] !== null) e.setAttribute(k, a[k]);
    if (txt !== undefined) e.textContent = txt;
    if (parent) parent.appendChild(e);
    return e;
  }
  function pts(p) { var o = []; for (var i = 0; i < p.length; i += 2) o.push(p[i] + ',' + p[i + 1]); return o.join(' '); }

  // 명세 web.ops → SVG(정지 이미지와 같은 1200 기준 좌표). 움직일 것은 묶음(g)별로 모아 둔다
  function draw(spec) {
    var w = spec.web, svg = el('svg', {viewBox: '0 0 ' + w.w + ' ' + w.h, 'aria-hidden': 'true', focusable: 'false', 'class': 'fig-anim'});
    var parts = [];
    w.ops.forEach(function (o) {
      var e;
      if (o.k === 't') {
        e = el('text', {x: o.x, y: o.y, 'text-anchor': {s: 'start', m: 'middle', e: 'end'}[o.a], 'font-size': o.s, 'font-weight': o.b ? 700 : 400, fill: o.c}, svg, o.t);
      } else if (o.k === 'l') {
        e = el(o.p.length > 4 ? 'polyline' : 'line', o.p.length > 4 ? {points: pts(o.p)} : {x1: o.p[0], y1: o.p[1], x2: o.p[2], y2: o.p[3]}, svg);
        e.setAttribute('fill', 'none'); e.setAttribute('stroke', o.c); e.setAttribute('stroke-width', o.w);
        e.setAttribute('stroke-linejoin', 'round');
        if (o.d) e.setAttribute('stroke-dasharray', o.d + ' ' + o.d);
      } else if (o.k === 'r') {
        var x = Math.min(o.x0, o.x1), y = Math.min(o.y0, o.y1), rw = Math.abs(o.x1 - o.x0), rh = Math.abs(o.y1 - o.y0), r = Math.max(0, Math.min(o.r, rw / 2, rh / 2));
        e = el('rect', {x: x, y: y, width: rw, height: rh, rx: r, fill: o.c}, svg);
      } else if (o.k === 'c') {
        e = el('circle', {cx: o.x, cy: o.y, r: o.r, fill: o.c}, svg);
      }
      if (e) parts.push({o: o, e: e});
    });
    return {svg: svg, parts: parts};
  }

  // 사이트 글꼴이 정지 이미지 글꼴(Noto Sans KR)보다 넓으면 그 폭에 맞춘다(오른쪽 끝 숫자가 잘리지 않게)
  function fitText(parts) {
    parts.forEach(function (p) {
      if (p.o.k !== 't' || !p.o.w) return;
      try { if (p.e.getComputedTextLength() > p.o.w * 1.04) { p.e.setAttribute('textLength', p.o.w); p.e.setAttribute('lengthAdjust', 'spacingAndGlyphs'); } } catch (x) { /* 무시 */ }
    });
  }

  function timeline(spec, d) {
    var g = window.gsap, tl = g.timeline({paused: true}), type = ((spec.figs || [])[0] || {}).type || '';
    var vertical = type === 'trend', items = {}, n = 0, lineX = [Infinity, -Infinity], LINE = 1.9, T0 = 0.15;
    d.parts.forEach(function (p) {
      var gr = p.o.g;
      if (typeof gr === 'number') { (items[gr] = items[gr] || []).push(p); n = Math.max(n, gr + 1); }
      if (gr === 'line' && p.o.k === 'l') for (var i = 0; i < p.o.p.length; i += 2) { lineX[0] = Math.min(lineX[0], p.o.p[i]); lineX[1] = Math.max(lineX[1], p.o.p[i]); }
    });
    var step = n ? Math.min(0.42, 1.9 / n) : 0, hasLine = lineX[0] < lineX[1];
    var fade = function (e, t, dur) { tl.fromTo(e, {opacity: 0}, {opacity: 1, duration: dur || 0.35, ease: 'power1.out'}, t); };
    // 막대·추이: 항목 차례로(이름 → 막대가 0 기준선에서 자람 → 숫자)
    Object.keys(items).forEach(function (k) {
      var t = T0 + (+k) * step;
      items[k].forEach(function (p) {
        var o = p.o;
        if (o.k === 'r') {
          var from = vertical ? {attr: {y: o.y0, height: 0}} : {attr: {x: o.x0, width: 0}};
          var to = vertical ? {attr: {y: Math.min(o.y0, o.y1), height: Math.abs(o.y1 - o.y0)}} : {attr: {x: Math.min(o.x0, o.x1), width: Math.abs(o.x1 - o.x0)}};
          to.duration = 0.6; to.ease = 'power2.out';
          tl.fromTo(p.e, from, to, t + 0.08);
        } else if (o.k === 't' && o.x <= 80 && o.a === 's') {
          fade(p.e, t, 0.3);  // 왼쪽 이름
        } else {
          fade(p.e, t + 0.5, 0.3);  // 숫자·범위 선·설명
        }
      });
    });
    var barsEnd = n ? T0 + (n - 1) * step + 0.9 : T0;
    // 선 그래프: 왼쪽에서 오른쪽으로 그려지고, 선이 사건 날짜에 닿을 때 그 사건 번호가 뜬다
    var at = function (x) { return T0 + LINE * Math.max(0, Math.min(1, (x - lineX[0]) / ((lineX[1] - lineX[0]) || 1))); };
    d.parts.forEach(function (p) {
      var o = p.o, gr = o.g;
      if (gr === 'line' && o.k === 'l' && hasLine) {
        var L = 0;
        try { L = p.e.getTotalLength(); } catch (x) { L = 0; }
        if (L > 0) { p.e.setAttribute('stroke-dasharray', L + ' ' + L); tl.fromTo(p.e, {strokeDashoffset: L}, {strokeDashoffset: 0, duration: LINE, ease: 'none'}, T0); }
      } else if (gr === 'end') {
        fade(p.e, (hasLine ? T0 + LINE : barsEnd) - 0.05, 0.4);
      } else if (gr === 'ref') {
        fade(p.e, hasLine ? T0 : barsEnd, 0.45);
      } else if (typeof gr === 'string' && gr.charAt(0) === 'e' && spec.web.gx && spec.web.gx[gr] !== undefined) {
        fade(p.e, at(spec.web.gx[gr]) - 0.05, 0.3);
      }
    });
    return tl;
  }

  var cache = {};
  function prepare(f) {
    if (f._fig) return f._fig;
    var url = f.getAttribute('data-fig');
    f._fig = Promise.all([cache[url] || (cache[url] = fetch(url).then(function (r) { if (!r.ok) throw r.status; return r.json(); })), loadGsap()])
      .then(function (r) {
        var spec = r[0], box = f.querySelector('.fig-box') || f, img = box.querySelector('img');
        if (!spec.web || !spec.web.ops || !window.gsap || !img) throw 'skip';
        var d = draw(spec);
        box.appendChild(d.svg);
        fitText(d.parts);
        var tl = timeline(spec, d);
        return function play() {
          box.classList.add('is-anim');  // 정지 이미지는 자리·대체 글(alt)을 지키고 투명하게, 그 위에 SVG
          tl.play(0);
        };
      });
    f._fig.catch(function () { /* 정지 이미지 그대로 */ });
    return f._fig;
  }

  // 가까워지면(아래 한 화면) 미리 준비, 30% 넘게 보이면 한 번만 재생
  var near = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (!e.isIntersecting) return;
      near.unobserve(e.target);
      // 스크롤 중 프레임을 빼앗지 않게 쉬는 틈에 준비(보이기 시작하면 seen 이 바로 준비)
      (window.requestIdleCallback || function (f) { return setTimeout(f, 200); })(function () { prepare(e.target); }, {timeout: 1500});
    });
  }, {rootMargin: '0px 0px 100% 0px'});
  var seen = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (!e.isIntersecting) return;
      seen.unobserve(e.target);
      prepare(e.target).then(function (play) { play(); }, function () {});
    });
  }, {threshold: 0.3});
  Array.prototype.forEach.call(figs, function (f) { near.observe(f); seen.observe(f); });
})();
