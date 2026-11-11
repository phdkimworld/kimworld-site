/* 이 리포트에 질문하기(2026-11-11): 리포트 본문만 근거로 답하는 리포트 도우미.
   서버(POST /v1/ask)에 키가 없거나 응답이 없으면 상자를 숨긴 채 둔다. */
(function () {
  var box = document.querySelector('[data-ask]');
  var KW = window.KW || {}, API = (KW.api || '').replace(/\/+$/, '');
  if (!box || !API || !window.fetch) return;
  var form = box.querySelector('[data-ask-form]'), ta = form.querySelector('textarea'), btn = box.querySelector('[data-ask-btn]');
  var out = box.querySelector('[data-ask-out]'), ans = box.querySelector('[data-ask-a]'), cnt = box.querySelector('[data-ask-n]');
  var max = 300, busy = false;
  function did() { try { return localStorage.getItem('kw-did') || ''; } catch (e) { return ''; } }
  fetch(API + '/v1/ask').then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
    if (!j || !j.on) return;
    if (j.max) { max = j.max; ta.maxLength = max; }
    var per = box.querySelector('[data-ask-per]'); if (per && j.per_day) per.textContent = j.per_day;
    box.hidden = false;
  }).catch(function () {});
  function count() { cnt.textContent = ta.value.length + '/' + max; }
  ta.addEventListener('input', count);
  function show(text, err) { ans.textContent = text; ans.className = 'ask-a' + (err ? ' is-err' : ''); out.hidden = false; }
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var q = ta.value.trim();
    if (busy || q.length < 2) return;
    busy = true; btn.disabled = true; btn.textContent = '찾는 중…';
    if (window.kwEv) kwEv('ask');
    var d = did(), u = API + '/v1/ask' + (/^[A-Za-z0-9_-]{22,64}$/.test(d) ? '?d=' + d : '');
    fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slug: box.getAttribute('data-slug'), q: q.slice(0, max) }) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (x) {
        if (x.ok && x.j.answer) { show(x.j.answer, false); return; }
        if (x.j.error === 'unavailable') { box.hidden = true; return; }
        show(x.j.message || '답을 만들지 못했습니다. 잠시 뒤에 다시 시도해 주세요.', true);
      })
      .catch(function () { show('연결이 원활하지 않습니다. 잠시 뒤에 다시 시도해 주세요.', true); })
      .then(function () { busy = false; btn.disabled = false; btn.textContent = '질문하기'; });
  });
})();
