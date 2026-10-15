// 설정 화면(/settings/): 푸시 알림(이 기기 켜기·종류별·일시 중지·방해 금지 시간) · 쪽지 받기 · 글자 크기 · 앱 · 계정
// community.js(window.KWC)가 먼저 준비돼야 해서 DOMContentLoaded에 시작한다(지연 스크립트는 모두 그 전에 실행된다)
document.addEventListener('DOMContentLoaded', function () {
  'use strict';
  var root = document.querySelector('[data-settings]'); if (!root) return;
  var C = window.KWC; if (!C) return;
  var $ = function (s) { return root.querySelector(s); }, $$ = function (s) { return Array.prototype.slice.call(root.querySelectorAll(s)); };
  var LS = function (k, v) { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { return null; } };

  // ---------- 화면: 글자 크기 ----------
  var curFont = document.documentElement.dataset.font || '';
  $$('[data-font]').forEach(function (r) {
    r.checked = r.value === curFont;
    r.addEventListener('change', function () {
      if (r.value) document.documentElement.dataset.font = r.value; else delete document.documentElement.dataset.font;
      LS('kw-font', r.value || null); C.flash('글자 크기를 바꿨습니다');
    });
  });
  // ---------- 앱: 이 기기 기록 지우기 ----------
  $('[data-clear-local]').addEventListener('click', function () {
    if (!confirm('이 기기의 최근 본 리포트와 저장한 리포트를 지울까요?')) return;
    LS('kw-saved', null); LS('kw-recent', null); C.flash('지웠습니다');
  });

  // ---------- 푸시 지원 여부 ----------
  var ua = navigator.userAgent;
  var ios = /iphone|ipad|ipod/i.test(ua) || (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
  var standalone = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
  var inapp = /kakaotalk|NAVER\(inapp|instagram|FBAN|FBAV|Line\/|DaumApps|; wv\)/i.test(ua);
  var supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window && location.protocol === 'https:';
  var stateEl = $('[data-push-state]'), helpEl = $('[data-push-help]'), onEl = $('[data-push-on]');
  var prefsBox = $('[data-push-prefs]'), testRow = $('[data-push-testrow]');
  function help(html) { helpEl.textContent = ''; if (!html) { helpEl.hidden = true; return; } helpEl.appendChild(html); helpEl.hidden = false; }
  function para(t) { var p = document.createElement('p'); p.textContent = t; return p; }
  function b64ToU8(s) { s = s.replace(/-/g, '+').replace(/_/g, '/'); var b = atob(s + '==='.slice((s.length + 3) % 4)), o = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) o[i] = b.charCodeAt(i); return o; }
  function reg() { return navigator.serviceWorker.getRegistration().then(function (r) { return r || navigator.serviceWorker.ready; }); }
  function curSub() { return supported ? reg().then(function (r) { return r && r.pushManager ? r.pushManager.getSubscription() : null; }).catch(function () { return null; }) : Promise.resolve(null); }

  var ME = null, PREFS = null, saving = 0;
  function paintPrefs(p) {
    PREFS = p;
    $$('[data-pref-on]').forEach(function (x) { x.checked = p[x.getAttribute('data-pref-on')] !== 'off'; });
    $$('[data-pref-who]').forEach(function (x) { x.checked = p[x.getAttribute('data-pref-who')] === x.value; });
    $('[data-pref-quiet]').checked = !!p.quiet; $('[data-quiet-times]').hidden = !p.quiet;
    var hm = function (m) { return ('0' + Math.floor(m / 60)).slice(-2) + ':' + ('0' + m % 60).slice(-2); };
    $('[data-pref-qfrom]').value = hm(p.qFrom); $('[data-pref-qto]').value = hm(p.qTo);
    var ps = $('[data-pause-state]'), sel = $('[data-pref-pause]');
    if (p.pause > Date.now()) {
      var d = new Date(p.pause); ps.textContent = d.toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' }) + '까지 멈춤';
      if (!sel.querySelector('option[value="keep"]')) { var o = document.createElement('option'); o.value = 'keep'; o.textContent = '멈춤 중'; sel.insertBefore(o, sel.firstChild.nextSibling); }
      sel.value = 'keep';
    } else { ps.textContent = '꺼져 있음'; sel.value = '0'; var k = sel.querySelector('option[value="keep"]'); if (k) k.remove(); }
  }
  function savePrefs(part) {
    saving++;
    return C.api('/v1/push/prefs', { method: 'POST', body: { prefs: part } }).then(function (d) {
      saving--; if (d && d.prefs) { paintPrefs(d.prefs); C.flash('저장했습니다'); } else C.flash('저장하지 못했습니다');
    }).catch(function () { saving--; C.flash('저장하지 못했습니다'); });
  }
  $$('[data-pref-on]').forEach(function (x) { x.addEventListener('change', function () { var o = {}; o[x.getAttribute('data-pref-on')] = x.checked ? 'on' : 'off'; savePrefs(o); }); });
  $$('[data-pref-who]').forEach(function (x) { x.addEventListener('change', function () { if (!x.checked) return; var o = {}; o[x.getAttribute('data-pref-who')] = x.value; savePrefs(o); }); });
  $('[data-pref-pause]').addEventListener('change', function (e) {
    var v = e.target.value; if (v === 'keep') return;
    savePrefs({ pause: v === '0' ? 0 : Date.now() + parseInt(v, 10) * 60000 });
  });
  var tz = new Date().getTimezoneOffset();
  $('[data-pref-quiet]').addEventListener('change', function (e) { $('[data-quiet-times]').hidden = !e.target.checked; savePrefs({ quiet: e.target.checked, tz: tz }); });
  var toMin = function (v) { var m = /^(\d\d):(\d\d)$/.exec(v || ''); return m ? +m[1] * 60 + +m[2] : null; };
  ['qfrom', 'qto'].forEach(function (k) {
    $('[data-pref-' + k + ']').addEventListener('change', function (e) {
      var m = toMin(e.target.value); if (m == null) return; var o = { tz: tz }; o[k === 'qfrom' ? 'qFrom' : 'qTo'] = m; savePrefs(o);
    });
  });

  function setState(on, text) { onEl.checked = !!on; stateEl.textContent = text; prefsBox.hidden = !on; testRow.hidden = !on; }
  function refresh() {
    if (!ME) {
      onEl.disabled = true; setState(false, '로그인하면 켤 수 있어요');
      var b = document.createElement('button'); b.type = 'button'; b.className = 'btn btn-small btn-primary'; b.textContent = '로그인하기';
      b.addEventListener('click', function () { C.openAccount(); });
      var w = document.createElement('div'); w.appendChild(para('팔로우한 종목의 새 리포트, 내 글의 답글·좋아요를 휴대폰 알림으로 받아 보세요.')); w.appendChild(b); help(w);
      return;
    }
    if (!supported) {
      onEl.disabled = true; setState(false, '이 브라우저에서는 쓸 수 없어요');
      if (ios && !standalone) {
        var w2 = document.createElement('div');
        w2.appendChild(para('아이폰은 김박사 월드를 홈 화면에 설치한 뒤 그 앱에서 알림을 켤 수 있어요.'));
        w2.appendChild(para('사파리에서 아래 공유 버튼(네모에 위 화살표) → \'홈 화면에 추가\' → 홈 화면의 김박사 월드 앱을 열고 이 화면에서 켜 주세요.'));
        help(w2);
      } else if (inapp) help(para('카카오톡·네이버 같은 앱 안 화면에서는 알림을 받을 수 없어요. 크롬이나 삼성 인터넷에서 열거나 앱을 설치해 주세요.'));
      else help(para('알림을 받으려면 크롬·삼성 인터넷·엣지·사파리(아이폰은 설치한 앱) 최신판에서 열어 주세요.'));
      return;
    }
    if (Notification.permission === 'denied') {
      onEl.disabled = true; setState(false, '알림이 차단돼 있어요');
      help(para(standalone ? '휴대폰 설정 → 알림 → 김박사 월드에서 알림을 허용한 뒤 다시 열어 주세요.' : '주소창 왼쪽 자물쇠(사이트 정보) → 알림 → 허용으로 바꾼 뒤 이 화면을 새로 열어 주세요.'));
      return;
    }
    help(null); onEl.disabled = false;
    curSub().then(function (s) {
      return C.api('/v1/push/prefs' + (s ? '?ep=' + encodeURIComponent(s.endpoint) : '')).then(function (d) {
        var on = !!(s && d.thisDevice);
        if (s && !d.thisDevice) { subscribeWith(s, true); on = true; } // 이 기기에 구독은 있는데 서버에 없으면(다른 계정이었거나 지워짐) 다시 묶는다
        paintPrefs(d.prefs);
        setState(on, on ? '켜져 있어요' : '꺼져 있어요');
        $('[data-push-devices]').textContent = d.devices > 1 ? '알림을 켠 기기 ' + d.devices + '대' : '';
      });
    }).catch(function () { setState(false, '상태를 불러오지 못했어요'); });
  }
  function subscribeWith(s, quiet) {
    return C.api('/v1/push/subscribe', { method: 'POST', body: { sub: s.toJSON ? s.toJSON() : s, tz: tz } }).then(function (d) {
      if (!d || !d.ok) throw new Error((d && d.message) || 'sub');
      if (!quiet) { C.flash('알림을 켰어요'); if (window.kwEv) kwEv('push_on'); }
    });
  }
  function turnOn() {
    onEl.disabled = true; stateEl.textContent = '켜는 중…';
    return Notification.requestPermission().then(function (perm) {
      if (perm !== 'granted') throw new Error(perm);
      return Promise.all([reg(), C.api('/v1/push/key')]);
    }).then(function (x) {
      var r = x[0], key = x[1].key;
      return r.pushManager.getSubscription().then(function (old) {
        return old || r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(key) });
      });
    }).then(function (s) { return subscribeWith(s); })
      .then(function () { onEl.disabled = false; refresh(); })
      .catch(function (e) { onEl.disabled = false; refresh(); if (String(e && e.message) !== 'default') C.flash('알림을 켜지 못했어요'); });
  }
  function turnOff() {
    onEl.disabled = true;
    return curSub().then(function (s) {
      if (!s) return;
      return C.api('/v1/push/unsubscribe', { method: 'POST', body: { endpoint: s.endpoint } }).then(function () { return s.unsubscribe(); });
    }).then(function () { onEl.disabled = false; C.flash('이 기기 알림을 껐어요'); refresh(); })
      .catch(function () { onEl.disabled = false; refresh(); });
  }
  onEl.addEventListener('change', function () { if (onEl.checked) turnOn(); else turnOff(); });
  $('[data-push-test]').addEventListener('click', function (e) {
    var b = e.target; b.disabled = true;
    C.api('/v1/push/test', { method: 'POST' }).then(function (d) {
      b.disabled = false; C.flash(d && d.ok ? '시험 알림을 보냈어요. 몇 초 안에 와요' : (d && d.message) || '보내지 못했어요. 알림을 껐다 다시 켜 보세요');
    }).catch(function () { b.disabled = false; });
  });

  // ---------- 계정·쪽지 받기 ----------
  C.meReady.then(function (me) {
    ME = me;
    var nm = $('[data-acct-name]'), sub = $('[data-acct-sub]'), ab = $('[data-acct-btn]');
    if (ME) {
      nm.textContent = ME.nick; sub.textContent = '프로필·닉네임·로그아웃'; ab.textContent = '계정 관리';
      $('[data-set-login-only]').hidden = false;
      var dp = ME.dmPref || 'all';
      $$('[data-dm-pref]').forEach(function (r) {
        r.checked = r.value === dp;
        r.addEventListener('change', function () {
          if (!r.checked) return;
          C.api('/v1/me', { method: 'POST', body: { dmPref: r.value } }).then(function (d) { C.flash(d && d.ok ? '저장했습니다' : '저장하지 못했습니다'); });
        });
      });
    }
    ab.addEventListener('click', function () { C.openAccount(); });
    refresh();
  });
  // 설치 같은 화면 밖 변화(권한 창을 닫고 돌아옴 등)
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible' && ME && !saving) refresh(); });
  if (location.hash === '#push' && !onEl.disabled) setTimeout(function () { var s = document.getElementById('push'); if (s) s.scrollIntoView(); }, 300);
});
