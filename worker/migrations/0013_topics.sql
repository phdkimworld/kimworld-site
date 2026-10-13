-- 종목·테마 팔로우: kind 't'(종목, key = 티커 대문자) | 'th'(테마, key = 테마 주소 이름)
CREATE TABLE IF NOT EXISTS topic_follows (uid INTEGER NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, created INTEGER NOT NULL, PRIMARY KEY (uid, kind, key));
CREATE INDEX IF NOT EXISTS topic_follows_key ON topic_follows (kind, key);
-- 새 리포트 알림을 이미 보낸 리포트(배포 때 한 번만 알리려고)
CREATE TABLE IF NOT EXISTS report_notified (slug TEXT PRIMARY KEY, created INTEGER NOT NULL);
