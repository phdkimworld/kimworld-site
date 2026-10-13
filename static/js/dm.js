// 쪽지함(/dm/): 대화 목록 · 요청함 · 대화 화면. 주소 ?t=대화번호, ?to=사람번호(새 대화)
// 새 쪽지는 화면을 보고 있을 때만 대화 화면 5초, 목록 30초마다 묻는다(서버 부담을 줄이려고 보이지 않을 때는 멈춤).
(function () {
  var C = window.KWC, root = document.querySelector('[data-dm]');
  if (!root) return;
  var msgEl = root.querySelector('[data-dm-msg]');
  if (!C) { msgEl.textContent = '쪽지 서버가 꺼져 있습니다.'; return; }
  var api = C.api, el = C.el, base = (window.KW || {}).base || '';
  var app = root.querySelector('[data-dm-app]'), listEl = root.querySelector('[data-dm-list]'), conv = root.querySelector('[data-dm-conv]');
  var msgsEl = root.querySelector('[data-dm-msgs]'), form = root.querySelector('[data-dm-form]'), input = root.querySelector('[data-dm-input]');
  var banner = root.querySelector('[data-dm-banner]'), cant = root.querySelector('[data-dm-cant]'), who = root.querySelector('[data-dm-who]'), pick = root.querySelector('[data-dm-pick]');
  var tab = 'inbox', threads = [], cur = null, lastId = 0, firstId = 0, pollT = 0, listT = 0, toUser = null;

  function qs(k) { return (new RegExp('[?&]' + k + '=(\\d+)').exec(location.search) || [])[1]; }
  function setUrl(q) { try { history.replaceState(null, '', base + '/dm/' + (q ? '?' + q : '')); } catch (e) {} }
  function time(ms) {
    var d = new Date(ms), now = new Date();
    if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' });
    return (d.getMonth() + 1) + '.' + d.getDate();
  }
  function dayLabel(ms) { return new Date(ms).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' }); }
  var visible = function () { return document.visibilityState === 'visible'; };

  // ---------- 목록 ----------
  function loadList() {
    return api('/v1/dm').then(function (d) {
      if (d._status === 401) return null;
      threads = d.items || [];
      C.setDm(d.dmUnread || 0, d.dmRequests || 0);
      var rn = root.querySelector('[data-dm-reqn]'); rn.textContent = d.dmRequests ? String(d.dmRequests) : '';
      drawList(); return d;
    });
  }
  function drawList() {
    listEl.textContent = '';
    var rows = threads.filter(function (t) { return tab === 'req' ? t.request : !t.request; });
    if (!rows.length) { listEl.appendChild(el('li', 'dm-empty muted', tab === 'req' ? '받은 요청이 없습니다.' : '아직 대화가 없습니다. 프로필의 "쪽지" 또는 "새 쪽지"로 시작해 보세요.')); return; }
    rows.forEach(function (t) {
      var li = el('li', 'dm-item' + (t.unread ? ' unread' : '') + (cur && cur.id === t.id ? ' on' : ''));
      var a = el('a', 'dm-link'); a.href = base + '/dm/?t=' + t.id;
      a.addEventListener('click', function (e) { e.preventDefault(); openThread(t.id); });
      a.appendChild(C.avatar(t.other.nick, t.other.id));
      var mid = el('span', 'dm-item-mid');
      var top = el('span', 'dm-item-top'); top.appendChild(el('strong', null, t.other.nick)); top.appendChild(el('span', 'muted dm-item-time', time(t.last.at)));
      mid.appendChild(top);
      mid.appendChild(el('span', 'dm-item-last', (t.last.mine ? '나: ' : '') + (t.last.body || '')));
      if (t.pending) mid.appendChild(el('span', 'dm-tag', '수락 대기'));
      a.appendChild(mid);
      if (t.unread) a.appendChild(el('span', 'dm-dot', ''));
      li.appendChild(a); listEl.appendChild(li);
    });
  }
  root.querySelectorAll('[data-dm-tab]').forEach(function (b) {
    b.addEventListener('click', function () {
      tab = b.getAttribute('data-dm-tab');
      root.querySelectorAll('[data-dm-tab]').forEach(function (x) { x.setAttribute('aria-selected', x === b ? 'true' : 'false'); });
      drawList();
    });
  });

  // ---------- 대화 ----------
  function showConv(on) {
    conv.hidden = !on; pick.hidden = on; app.classList.toggle('dm-in-conv', on);
  }
  function msgItem(m) {
    var li = el('li', 'dm-m' + (m.mine ? ' mine' : '') + (m.status !== 'ok' ? ' gone' : '')); li.setAttribute('data-mid', m.id);
    var bub = el('div', 'dm-bub');
    if (m.status === 'ok') { C.richText(bub, m.body); } else bub.textContent = m.status === 'hidden' ? '운영자가 가린 쪽지입니다.' : '삭제된 쪽지입니다.';
    li.appendChild(bub);
    var meta = el('span', 'dm-meta muted', new Date(m.at).toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' }));
    li.appendChild(meta);
    if (m.status === 'ok') {
      var mb = el('button', 'dm-mbtn', '⋯'); mb.type = 'button'; mb.setAttribute('aria-label', '쪽지 메뉴');
      mb.addEventListener('click', function () { msgMenu(m, li); });
      li.appendChild(mb);
    }
    return li;
  }
  function msgMenu(m, li) {
    var body = C.dialog('쪽지');
    if (m.mine) body.appendChild(C.btn('이 쪽지 지우기(상대 화면에서도)', 'btn', function () {
      api('/v1/dm/msg/' + m.id + '/delete', { method: 'POST' }).then(function () { m.status = 'deleted'; li.replaceWith(msgItem(m)); closeDlg(); });
    }));
    else {
      body.appendChild(C.btn('신고하기', 'btn', function () {
        if (!confirm('이 쪽지를 신고할까요? 운영자가 신고된 쪽지만 확인합니다.')) return;
        api('/v1/dm/msg/' + m.id + '/report', { method: 'POST' }).then(function (r) { closeDlg(); C.flash(r.message || '신고했습니다'); });
      }));
    }
    if (navigator.clipboard && m.body) body.appendChild(C.btn('내용 복사', 'btn', function () { navigator.clipboard.writeText(m.body); closeDlg(); C.flash('복사했습니다'); }));
  }
  function closeDlg() { var d = document.querySelector('dialog.kw-dlg[open]'); if (d) d.close(); }
  function addMsgs(items, prepend) {
    if (!items.length) return;
    var frag = document.createDocumentFragment(), prevDay = '';
    var edge = prepend ? msgsEl.firstElementChild : msgsEl.lastElementChild;
    if (!prepend) { var lastM = [].slice.call(msgsEl.querySelectorAll('.dm-m')).pop(); prevDay = lastM ? lastM.getAttribute('data-day') : ''; }
    items.forEach(function (m) {
      var dl = dayLabel(m.at);
      if (dl !== prevDay) { frag.appendChild(el('li', 'dm-day muted', dl)); prevDay = dl; }
      var it = msgItem(m); it.setAttribute('data-day', dl); frag.appendChild(it);
    });
    if (prepend) msgsEl.insertBefore(frag, edge); else msgsEl.appendChild(frag);
    void edge;
  }
  function drawSeen(upTo) {
    msgsEl.querySelectorAll('.dm-seen').forEach(function (n) { n.remove(); });
    var mine = [].slice.call(msgsEl.querySelectorAll('.dm-m.mine')).filter(function (n) { return +n.getAttribute('data-mid') <= upTo; }).pop();
    if (mine) mine.appendChild(el('span', 'dm-seen muted', '읽음'));
  }
  function drawHead(th) {
    who.textContent = ''; who.href = C.profileUrl(th.other.id);
    who.appendChild(C.avatar(th.other.nick, th.other.id)); who.appendChild(el('strong', null, th.other.nick));
    banner.hidden = true; banner.textContent = '';
    if (th.request) {
      banner.hidden = false;
      banner.appendChild(el('p', null, th.other.nick + '님이 쪽지를 보냈어요. 답장하거나 수락하면 대화가 시작됩니다. 상대는 수락 전까지 내가 읽었는지 알 수 없어요.'));
      var row = el('div', 'kw-row');
      row.appendChild(C.btn('수락', 'btn btn-primary', function () { api('/v1/dm/' + th.id + '/accept', { method: 'POST' }).then(function () { openThread(th.id); loadList(); }); }));
      row.appendChild(C.btn('삭제', 'btn', function () { delThread(th); }));
      row.appendChild(C.btn('차단', 'btn', function () { block(th); }));
      banner.appendChild(row);
    } else if (th.pending) {
      banner.hidden = false; banner.appendChild(el('p', null, th.other.nick + '님이 요청을 수락하면 이어서 보낼 수 있어요.'));
    }
    var warn = el('p', 'dm-safety', '⚠️ 리딩방·외부 채팅방 초대, 입금·투자 대행 요구는 사기입니다. 이런 쪽지는 신고해 주세요.');
    banner.hidden = false; banner.appendChild(warn);
    form.hidden = !th.can; cant.hidden = th.can || th.pending; cant.textContent = th.reason || '';
  }
  function openThread(tid, keepUrl) {
    clearTimeout(pollT);
    return api('/v1/dm/' + tid).then(function (d) {
      if (d._status !== 200) { C.flash('대화를 찾지 못했습니다'); return; }
      cur = d.thread; toUser = null; msgsEl.textContent = '';
      lastId = 0; firstId = 0;
      drawHead(cur);
      if (d.more) {
        var mo = el('li', 'dm-older'); var mb = C.btn('이전 쪽지 보기', 'cm-link', function () { older(mo); }); mo.appendChild(mb); msgsEl.appendChild(mo);
      }
      addMsgs(d.items);
      if (d.items.length) { lastId = d.items[d.items.length - 1].id; firstId = d.items[0].id; }
      drawSeen(cur.seenUpTo);
      showConv(true); if (!keepUrl) setUrl('t=' + tid);
      msgsEl.scrollTop = msgsEl.scrollHeight;
      threads.forEach(function (t) { if (t.id === tid) t.unread = false; }); drawList();
      if (window.kwEv) kwEv('dm_open');
      poll();
      if (matchMedia('(min-width: 760px)').matches) input.focus();
    });
  }
  function older(mo) {
    api('/v1/dm/' + cur.id + '?before=' + firstId).then(function (d) {
      mo.remove();
      var h0 = msgsEl.scrollHeight;
      addMsgs(d.items, true);
      if (d.items.length) firstId = d.items[0].id;
      if (d.items.length === 50) { var m2 = el('li', 'dm-older'); m2.appendChild(C.btn('이전 쪽지 보기', 'cm-link', function () { older(m2); })); msgsEl.insertBefore(m2, msgsEl.firstChild); }
      msgsEl.scrollTop += msgsEl.scrollHeight - h0;
    });
  }
  function poll() {
    clearTimeout(pollT);
    pollT = setTimeout(function () {
      if (!cur || !visible()) { poll(); return; }
      api('/v1/dm/' + cur.id + '?after=' + lastId).then(function (d) {
        if (d._status !== 200) return;
        var near = msgsEl.scrollHeight - msgsEl.scrollTop - msgsEl.clientHeight < 120;
        var fresh = (d.items || []).filter(function (m) { return m.id > lastId; });
        addMsgs(fresh);
        if (fresh.length) lastId = fresh[fresh.length - 1].id;
        var wasReq = cur.request || cur.pending; cur = d.thread; if (wasReq && !cur.request && !cur.pending) drawHead(cur);
        drawSeen(cur.seenUpTo);
        if (fresh.length && near) msgsEl.scrollTop = msgsEl.scrollHeight;
        poll();
      }).catch(function () { poll(); });
    }, 5000);
  }
  function startWith(uid) { // 프로필의 "쪽지" 또는 새 쪽지에서 사람을 골랐을 때
    return api('/v1/dm/with/' + uid).then(function (d) {
      if (d._status !== 200) { C.flash('상대를 찾지 못했습니다'); return; }
      if (d.tid) { openThread(d.tid); return; }
      cur = null; toUser = d.other; clearTimeout(pollT); msgsEl.textContent = '';
      drawHead({ id: 0, other: d.other, can: d.can, reason: d.reason, request: false, pending: false });
      if (d.can && d.request) banner.insertBefore(el('p', null, '처음 보내는 쪽지는 상대의 요청함으로 갑니다. 상대가 수락하기 전에는 한 통만 보낼 수 있어요.'), banner.firstChild);
      msgsEl.appendChild(el('li', 'dm-day muted', d.other.nick + '님과 새 대화'));
      showConv(true); setUrl('to=' + uid);
      if (d.can) input.focus();
    });
  }
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = input.value.trim(); if (!text) return;
    var sb = form.querySelector('[data-dm-send]'); sb.disabled = true;
    api('/v1/dm/send', { method: 'POST', body: cur ? { tid: cur.id, body: text } : { to: toUser.id, body: text } }).then(function (r) {
      sb.disabled = false;
      if (!r.ok) { C.flash(r.message || '보내지 못했습니다'); return; }
      input.value = ''; autoGrow();
      if (window.kwEv) kwEv('dm_send');
      if (!cur) { openThread(r.tid); loadList(); return; }
      addMsgs([{ id: r.id, mine: true, body: text, status: 'ok', at: r.at }]); lastId = Math.max(lastId, r.id);
      msgsEl.scrollTop = msgsEl.scrollHeight;
      if (r.accepted !== cur.accepted) { cur.accepted = r.accepted; }
      if (!r.accepted) { cur.pending = true; cur.can = false; drawHead(cur); }
      loadList();
    }).catch(function () { sb.disabled = false; C.flash('보내지 못했습니다. 잠시 뒤 다시 시도해 주세요'); });
  });
  function autoGrow() { input.style.height = 'auto'; input.style.height = Math.min(140, input.scrollHeight) + 'px'; }
  input.addEventListener('input', autoGrow);
  input.addEventListener('keydown', function (e) { // PC: Enter로 보내기, Shift+Enter 줄바꿈
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && matchMedia('(min-width: 760px)').matches) { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event('submit')); }
  });
  function delThread(th) {
    if (!confirm('이 대화를 내 쪽지함에서 지울까요? 상대 쪽지함에는 남습니다.')) return;
    api('/v1/dm/' + th.id + '/delete', { method: 'POST' }).then(function () { cur = null; showConv(false); setUrl(''); loadList(); });
  }
  function block(th) {
    if (!confirm(th.other.nick + '님을 차단할까요? 서로 쪽지·팔로우를 할 수 없게 됩니다.')) return;
    api('/v1/block', { method: 'POST', body: { uid: th.other.id } }).then(function (r) {
      if (r.blocked) { C.setBlocked(th.other.id, true); C.flash('차단했습니다'); if (window.kwEv) kwEv('block'); }
      if (th.id) openThread(th.id); else startWith(th.other.id);
    });
  }
  root.querySelector('[data-dm-back]').addEventListener('click', function () { cur = null; toUser = null; clearTimeout(pollT); showConv(false); setUrl(''); loadList(); });
  root.querySelector('[data-dm-menu]').addEventListener('click', function () {
    var th = cur || (toUser ? { id: 0, other: toUser } : null); if (!th) return;
    var body = C.dialog(th.other.nick);
    var pf = el('a', 'btn', '프로필 보기'); pf.href = C.profileUrl(th.other.id); body.appendChild(pf);
    body.appendChild(C.btn('차단하기', 'btn', function () { closeDlg(); block(th); }));
    if (th.id) body.appendChild(C.btn('대화 지우기', 'btn', function () { closeDlg(); delThread(th); }));
    body.appendChild(el('p', 'muted kw-small', '쪽지 하나를 신고하려면 그 쪽지 옆 ⋯을 누르세요.'));
  });
  // 새 쪽지: 닉네임으로 찾기
  root.querySelector('[data-dm-new]').addEventListener('click', function () {
    var body = C.dialog('새 쪽지');
    var inp = el('input'); inp.placeholder = '닉네임으로 찾기'; inp.autocomplete = 'off'; inp.maxLength = 12;
    body.appendChild(inp);
    var ul = el('ul', 'kw-users'); body.appendChild(ul);
    var t = 0;
    inp.addEventListener('input', function () {
      clearTimeout(t);
      t = setTimeout(function () {
        var q = inp.value.trim(); ul.textContent = ''; if (!q) return;
        api('/v1/users/search?q=' + encodeURIComponent(q)).then(function (d) {
          ul.textContent = '';
          var me = C.state().me;
          var items = (d.items || []).filter(function (u) { return !me || u.id !== me.id; });
          if (!items.length) { ul.appendChild(el('li', 'muted', '찾는 사람이 없습니다.')); return; }
          items.forEach(function (u) {
            var li = el('li', 'kw-user kw-user-pick'); li.tabIndex = 0;
            li.appendChild(C.avatar(u.nick, u.id));
            var w = el('div', 'kw-user-who'); w.appendChild(el('strong', null, u.nick)); if (u.bio) w.appendChild(el('span', 'muted kw-small', u.bio)); li.appendChild(w);
            var go = function () { closeDlg(); startWith(u.id); };
            li.addEventListener('click', go); li.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
            ul.appendChild(li);
          });
        });
      }, 250);
    });
    setTimeout(function () { inp.focus(); }, 50);
  });

  // ---------- 시작 ----------
  C.meReady.then(function (me) {
    if (!me) {
      msgEl.textContent = '';
      msgEl.appendChild(document.createTextNode('쪽지는 로그인하고 닉네임을 정한 뒤 쓸 수 있습니다. '));
      msgEl.appendChild(C.btn('로그인', 'btn btn-primary', C.openAccount));
      return;
    }
    msgEl.hidden = true; app.hidden = false;
    loadList().then(function () {
      var t = qs('t'), to = qs('to');
      if (t) openThread(+t, true); else if (to) startWith(+to);
    });
    (function tick() { listT = setTimeout(function () { if (visible()) loadList().catch(function () {}); tick(); }, 30000); })();
  });
})();
