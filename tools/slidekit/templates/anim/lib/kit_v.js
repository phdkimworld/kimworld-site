// 쇼츠 세로 anim 공통(v_stat·v_bars·v_line). 입력 window.ANIM = {data, t:{beats:[초…], *_beat:초}, dur, cover}
// cover=true(쇼츠 첫 장면): 0.0초 프레임이 표지 — data-cover 요소(이름·꼬리표 = name, 160px 이상 숫자 = big)는 0초에 최종 크기·불투명으로 그리고
//   움직이지 않는다. 움직임은 0.5초부터 다른 요소에. anim.py가 0초에 scene.cover()로 확인한다(COVER_FAIL이면 렌더를 멈춤)
// 계약: window.scene = {dur, ready, seek(t), beats, spans, frame:[0,0,1080,768], cover()}
const A = window.ANIM || {data: {}, t: {}, dur: 5}, d = A.data || {}, T = A.t || {}, COVER = !!A.cover, DUR = A.dur || 5;
const W = 1080, H = 768, SAFE_Y = 576, SAFE_X = 900, NS = 'http://www.w3.org/2000/svg';
const COL = {red: '#FF4D4D', green: '#39D98A', gold: '#F5B83D', white: '#ffffff', mute: '#B0BED0', bar: '#4A6688', line: '#283B57'};
const esc = s => String(s == null ? '' : s).replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));
// 글자 하나: 가운데 cx, 위 y, 크기 size(최대 폭 maxw 넘으면 줄이되 min 아래로는 안 줄임). 아래 안전 구역(y ≥ 576)이면 가운데 450·폭 820으로
function txt(text, o) {
  o = o || {}; const e = document.createElement('div'); e.className = 't ' + (o.cls || ''); e.innerHTML = esc(text);
  if (o.box !== false) e.setAttribute('data-box', ''); if (o.cover) e.setAttribute('data-cover', o.cover);
  let size = o.size || 72; e.style.fontSize = size + 'px'; document.body.appendChild(e);
  const low = (o.y || 0) + size * 0.9 >= SAFE_Y, cx = o.cx !== undefined ? o.cx : (low ? 450 : 540), maxw = o.maxw || (low ? 820 : 980);
  while (e.offsetWidth > maxw && size > (o.min || 40)) { size -= 4; e.style.fontSize = size + 'px'; }
  e.style.left = (cx - e.offsetWidth / 2) + 'px'; e.style.top = (o.y || 0) + 'px'; e._size = size; return e;
}
function el(t, a, p) { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); (p || svg()).appendChild(e); return e; }
let _sv = null; function svg() { if (!_sv) { _sv = document.createElementNS(NS, 'svg'); _sv.setAttribute('class', 'stage'); _sv.setAttribute('width', W); _sv.setAttribute('height', H); document.body.prepend(_sv); } return _sv; }
function fmtv(v, unit, dec, text) {
  if (text) return text; if (v === null || v === undefined) return '';
  unit = unit === undefined ? (d.unit || '') : unit; dec = dec === undefined ? (d.decimals === undefined ? 1 : d.decimals) : dec;
  const s = Math.abs(v).toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec});
  return (unit === '%' ? (v > 0 ? '+' : v < 0 ? '-' : '') : (v < 0 ? '-' : '')) + s + unit;
}
// 사건 시각: beats(초)가 있으면 그대로, 없으면 첫 사건 0.5초(표지 뒤)부터 장면 길이에 고르게(간격 2.4초 이하 — 정지 3초 실패 방지)
function times(n, first) {
  const bt = (T.beats || []).filter(x => x != null), at = [], f = first === undefined ? 0.5 : first;
  const step = Math.min(2.4, Math.max(0.6, (DUR - f - 0.8) / Math.max(1, n)));
  for (let i = 0; i < n; i++) at.push(bt[i] !== undefined ? Math.max(bt[i], i ? at[i - 1] + .4 : (COVER ? 0.4 : 0.2)) : f + i * step);
  return at;
}
// 장면 끝까지 3초 넘게 멈추지 않도록: 마지막 사건 뒤 남은 시간이 길면 강조 상자를 하나 더 띄운다(target 둘레)
function keepAlive(tl, last, target) {
  if (!target || DUR - last < 2.6) return last;
  const r = target.getBoundingClientRect(), b = document.createElement('div'); b.className = 'box';
  Object.assign(b.style, {left: (r.left - 18) + 'px', top: (r.top - 8) + 'px', width: (r.width + 36) + 'px', height: (r.height + 16) + 'px'}); document.body.insertBefore(b, document.body.firstChild.nextSibling);
  const at = Math.min(DUR - 0.6, last + Math.min(2.2, (DUR - last) / 2));
  tl.set(b, {opacity: 0}, 0).fromTo(b, {opacity: 0, scale: 1.12}, {opacity: 1, scale: 1, duration: .3, ease: 'power2.out', immediateRender: false}, at);
  return at + .3;
}
// 초점 띠: 박자마다 지금 말하는 항목 칸에 노란 띠가 옮겨 간다(작은 막대·점만 바뀌면 쇼츠 정지 검사(화소 1%)에 안 잡혀 '정지 3초'가 됨, 11-16 시험)
function band(tl, rects, at) {
  const b = document.createElement('div'); b.className = 'band'; document.body.insertBefore(b, document.body.firstChild);
  rects.forEach((r, i) => { if (i === 0) { tl.set(b, {left: r[0], top: r[1], width: r[2], height: r[3], opacity: COVER ? 0 : 1}, 0); return; }
    tl.to(b, {left: r[0], top: r[1], width: r[2], height: r[3], opacity: 1, duration: .3, ease: 'power2.inOut'}, at[i]); });
  return b;
}
function finish(tl, end, beats) {
  tl.to({}, {duration: .01}, end);
  window.scene = {dur: end, ready: document.fonts.ready, beats, frame: [0, 0, W, H],
    spans: tl.getChildren(true, true, false).map(c => [c.startTime(), c.endTime()]),
    seek(t) { tl.seek(Math.min(Math.max(t, 1e-4), tl.duration()), false); },
    cover() { return [...document.querySelectorAll('[data-cover]')].map(e => { const r = e.getBoundingClientRect(); let op = 1, tf = [];
      for (let x = e; x && x.nodeType === 1; x = x.parentElement) { const s = getComputedStyle(x); op *= +s.opacity; if (s.visibility === 'hidden' || s.display === 'none') op = 0; if (s.transform && s.transform !== 'none') tf.push(s.transform); }
      return {role: e.getAttribute('data-cover'), text: e.textContent.trim().slice(0, 24), x: r.left, y: r.top, w: r.width, h: r.height, fs: parseFloat(getComputedStyle(e).fontSize), op, tf}; }); }};
  scene.seek(0);
}
// 표지 요소(이름·숫자) 공통: 표지면 0초부터 최종 상태, 아니면 0~0.35초에 튀어 들어온다(숫자는 count면 같은 자릿수로 카운트업 0.6초)
function enter(tl, e, t0, count) {
  if (COVER) return;
  const s = e.textContent, m = count && s.match(/[-+]?\d[\d,]*(\.\d+)?/g);
  tl.fromTo(e, {opacity: .3, scale: .82}, {opacity: 1, scale: 1, duration: .35, ease: 'back.out(1.8)', immediateRender: true}, t0);
  if (m && m.length === 1) { const tk = m[0], v = parseFloat(tk.replace(/,/g, '')), dec = (tk.split('.')[1] || '').length, i = s.indexOf(tk), o = {x: 0};
    tl.to(o, {x: 1, duration: .6, ease: 'power2.out', onUpdate() { e.textContent = o.x >= 1 ? s : s.slice(0, i) + (v < 0 ? '-' : tk[0] === '+' ? '+' : '') + Math.abs(v * o.x).toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec, useGrouping: tk.includes(',')}) + s.slice(i + tk.length); }}, t0); }
}
