-- 리포스트: 리포트(kind 'r', ref = 리포트 주소 이름) 또는 남의 글(kind 'p', ref = 글 번호)을 내 프로필·팔로워 피드로 다시 올린다
CREATE TABLE IF NOT EXISTS reposts (uid INTEGER NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL, created INTEGER NOT NULL, PRIMARY KEY (uid, kind, ref));
CREATE INDEX IF NOT EXISTS reposts_ref ON reposts (kind, ref);
CREATE INDEX IF NOT EXISTS reposts_uid ON reposts (uid, created);
