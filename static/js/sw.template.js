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
