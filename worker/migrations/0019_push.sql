-- 0019: 웹 푸시 알림(2026-10-14) — 앱(홈 화면에 설치한 웹앱)·브라우저에 알림을 보낸다
-- · push_subs: 기기마다 푸시 구독 하나(계정에 묶는다. 로그인해야 켤 수 있다)
-- · push_prefs: 계정별 알림 설정(JSON). 알림 종류별 켬·끔·'내가 팔로우한 사람만', 일시 중지, 방해 금지 시간
-- · push_pending: 보낼 알림 대기열. 같은 대상·종류는 한 줄로 모은다(좋아요 100개 → 한 번). 1분마다 워커 예약 작업이 보낸다
-- · app_keys: 서버가 처음 한 번 만드는 VAPID 키(푸시 서비스에 '우리 서버가 보낸 알림'임을 증명)
CREATE TABLE IF NOT EXISTS push_subs (endpoint TEXT PRIMARY KEY, uid INTEGER NOT NULL, p256dh TEXT NOT NULL, auth TEXT NOT NULL, ua TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL, last_ok INTEGER NOT NULL DEFAULT 0, fails INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS push_subs_uid ON push_subs (uid);
CREATE TABLE IF NOT EXISTS push_prefs (uid INTEGER PRIMARY KEY, prefs TEXT NOT NULL DEFAULT '{}', updated INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS push_pending (uid INTEGER NOT NULL, type TEXT NOT NULL, ref TEXT NOT NULL, slug TEXT NOT NULL DEFAULT '', from_nick TEXT NOT NULL DEFAULT '', n INTEGER NOT NULL DEFAULT 1,
  updated INTEGER NOT NULL, pushed INTEGER NOT NULL DEFAULT 0, pushed_at INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (uid, type, ref));
CREATE INDEX IF NOT EXISTS push_pending_todo ON push_pending (updated, pushed);
CREATE TABLE IF NOT EXISTS app_keys (k TEXT PRIMARY KEY, v TEXT NOT NULL);
