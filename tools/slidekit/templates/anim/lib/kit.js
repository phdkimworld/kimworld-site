// anim 데이터 틀 공통(머리줄·제목·출처·SVG 도우미·박자·장면 계약). 입력 window.ANIM = {data, t:{beats:[초…], *_beat:초}, dur, ticker, name}
// 규칙: 첫 프레임부터 제목·축·첫 항목·첫 숫자가 보인다(페이드인 없이 컷 시작). 숫자는 data에 준 값만(사이 값을 굴리지 않는다).
// 항목 i(1부터)는 beats[i-1]초에 뜬다(내레이션 문장 시작). 없으면 1.2초부터 고르게.
const A = window.ANIM || {data: {}, t: {}, dur: 9}, d = A.data || {}, T = A.t || {}, $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const COL = {gold: '#F5B83D', red: '#FF4D5E', green: '#3DDC97', blue: '#4FA3FF', ink: '#E6EDF5', white: '#ffffff', mute: '#9FB3CC', soft: '#C9D6E6', dim: '#6F829B', line: '#22385A', bar: '#4A6688', panel: 'rgba(22,37,59,.92)'};
function el(t, a, p, txt) { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); if (txt !== undefined) e.textContent = txt; (p || $('sv')).appendChild(e); return e; }
function frame() {
  const esc = s => String(s == null ? '' : s).replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));
  document.body.insertAdjacentHTML('afterbegin', `<div class="bg"></div><div class="grid"></div>
<div class="hdr">${A.ticker ? `<span class="tk">${esc(A.ticker)}</span>` : ''}<span>${esc(A.name)}</span>${d.kicker ? `<span class="kick">${esc(d.kicker)}</span>` : ''}<span class="brand">김박사 월드</span></div>
<h1 data-box>${esc(Array.isArray(d.title) ? d.title.join(' ') : d.title)}</h1>${d.sub ? `<div class="sub" data-box>${esc(d.sub)}</div>` : ''}
<svg class="stage" id="sv" width="1920" height="1080" viewBox="0 0 1920 1080"></svg><div class="ftr">${esc([d.note, d.source].filter(Boolean).join(' · '))}</div>`);
}
// 숫자 표기: text가 있으면 그대로, 없으면 단위에 맞춰(퍼센트는 부호 붙임)
function fmtv(v, unit, dec, text) {
  if (text) return text; if (v === null || v === undefined) return '';
  unit = unit === undefined ? (d.unit === undefined ? '' : d.unit) : unit; dec = dec === undefined ? (d.decimals === undefined ? 1 : d.decimals) : dec;
  let s = Math.abs(v).toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec});
  if (unit === '%') return (v > 0 ? '+' : v < 0 ? '-' : '') + s + '%';
  return (v < 0 ? '-' : '') + s + (unit || '');
}
// 숫자 색(2026-11-24): 강조 항목(hi)이 있으면 그것만 금색, 나머지는 맥락 회색(강조색 하나 — 대형 채널·BBC 그래프 원칙). 강조가 없을 때만 퍼센트 부호 색
const ANY_HI = (d.items || d.series || []).some(x => x && x.hi);
function signCol(v, hi) { if (hi) return COL.gold; if (ANY_HI) return COL.soft; if ((d.unit || '') !== '%' || !v) return COL.white; return v < 0 ? COL.red : COL.green; }
// 박자 시각표: at[0]=0(첫 항목은 첫 프레임부터), at[i]=beats[i-1](없으면 고르게), 서로 0.5초 이상 띄움
function times(n, first, gap) {
  const bt = (T.beats || []).filter(x => x != null), at = [0];
  for (let i = 1; i < n; i++) at.push(bt[i - 1] !== undefined ? Math.max(bt[i - 1], at[i - 1] + .5) : (i == 1 ? (first || 1.2) : at[i - 1] + (gap || 1.3)));
  return at;
}
function beatAt(key, after) { const v = T[key]; return v != null ? Math.max(v, after) : after + .9; }
// 장면 계약: dur(움직임 끝), ready(글꼴), seek(t)(그 시각 화면 그대로, 결정적), beats(겹침 검사 시각)
function finish(tl, end, beats, onSeek) {
  tl.to({}, {duration: .01}, end);
  window.scene = {dur: end, ready: document.fonts.ready, beats: beats, spans: tl.getChildren(true, true, false).map(c => [c.startTime(), c.endTime()]), seek(t) { tl.seek(Math.min(Math.max(t, 1e-4), tl.duration()), false); if (onSeek) onSeek(); }};  // 0초의 set도 첫 프레임에 반영
  scene.seek(0);
}
// 축 눈금: 범위에서 4~6개
function ticks(lo, hi) { const raw = (hi - lo) / 5, mag = Math.pow(10, Math.floor(Math.log10(raw || 1))), step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw); const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10)); return {list: out, step}; }
// 세로로 겹치는 이름표를 최소 간격으로 벌린다(ys: 원하는 y 목록 → 고친 y 목록)
function spread(ys, gap, lo, hi) {
  const o = ys.map((y, i) => ({y, i})).sort((a, b) => a.y - b.y);
  for (let k = 1; k < o.length; k++) if (o[k].y - o[k - 1].y < gap) o[k].y = o[k - 1].y + gap;
  if (o.length && o[o.length - 1].y > hi) { o[o.length - 1].y = hi; for (let k = o.length - 2; k >= 0; k--) if (o[k + 1].y - o[k].y < gap) o[k].y = o[k + 1].y - gap; }
  if (o.length && o[0].y < lo) { o[0].y = lo; for (let k = 1; k < o.length; k++) if (o[k].y - o[k - 1].y < gap) o[k].y = o[k - 1].y + gap; }
  const r = []; o.forEach(x => r[x.i] = x.y); return r;
}
