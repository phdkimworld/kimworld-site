// 김박사 월드 웹앱 서비스 워커(빌드가 sw.js로 만든다). 빌드마다 버전이 바뀌어 옛 캐시는 지운다.
// · 페이지: 인터넷 먼저, 끊기면 저장해 둔 페이지 → 없으면 오프라인 안내
// · /static/ 파일(주소에 버전이 붙음): 저장본 먼저
// · API(api.drkimworld.com)·광고 등 다른 주소는 건드리지 않는다
const V = 'kw-__VER__', BASE = '__BASE__', OFF = BASE + '/offline/';
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(V).then((c) => c.addAll([OFF, BASE + '/static/icon-192.png'])).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== V).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.origin !== self.location.origin) return;
  if (r.mode === 'navigate') {
    e.respondWith(fetch(r).then((res) => {
      if (res.ok && !u.pathname.startsWith(BASE + '/admin/')) { const cp = res.clone(); caches.open(V).then((c) => c.put(u.pathname, cp)); }
      return res;
    }).catch(() => caches.match(u.pathname).then((m) => m || caches.match(OFF))));
    return;
  }
  if (u.pathname.startsWith(BASE + '/static/')) {
    e.respondWith(caches.match(r).then((m) => m || fetch(r).then((res) => {
      if (res.ok) { const cp = res.clone(); caches.open(V).then((c) => c.put(r, cp)); }
      return res;
    })));
  }
});

// ---------- 푸시 알림(2026-10-14): 서버가 보낸 {t: 제목, b: 내용, u: 열 주소, g: 묶음 이름}을 띄운다 ----------
// 같은 묶음(g, 예: 같은 글의 좋아요)은 한 칸을 덮어쓴다. 누르면 열려 있는 창을 그 주소로, 없으면 새로 연다
self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { t: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.t || '김박사 월드', {
    body: d.b || '', icon: BASE + '/static/icon-192.png', badge: BASE + '/static/badge-96.png', // 상태 표시줄용 흰색 단색 아이콘(안드로이드는 색을 지우고 모양만 쓴다)
    tag: d.g || undefined, renotify: !!d.g, data: { u: d.u || '/' }, lang: 'ko',
  }));
});
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = new URL(BASE + ((e.notification.data && e.notification.data.u) || '/'), self.location.origin).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((cs) => {
    for (const c of cs) {
      if (new URL(c.url).origin === self.location.origin && 'focus' in c) {
        return c.focus().then((w) => (w && 'navigate' in w ? w.navigate(url) : self.clients.openWindow(url))).catch(() => self.clients.openWindow(url));
      }
    }
    return self.clients.openWindow(url);
  }));
});
// 브라우저가 구독을 바꾸면(만료 등) 서버에 새로 알린다(로그인 쿠키로 계정에 묶인다)
self.addEventListener('pushsubscriptionchange', (e) => {
  const opts = e.oldSubscription && e.oldSubscription.options;
  if (!opts) return;
  e.waitUntil(self.registration.pushManager.subscribe(opts).then((s) => fetch('__API__/v1/push/subscribe', {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sub: s.toJSON() }),
  })).catch(() => {}));
});
