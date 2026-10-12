-- 계정 키 계정(개인정보 없음): 브라우저가 만든 무작위 키의 해시(actor)에 닉네임을 붙인다
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL UNIQUE,
  nick TEXT NOT NULL,
  nick_lc TEXT NOT NULL UNIQUE,
  bio TEXT NOT NULL DEFAULT '',
  created INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'ok'   -- ok | banned
);
CREATE TABLE IF NOT EXISTS follows (follower INTEGER NOT NULL, followee INTEGER NOT NULL, created INTEGER NOT NULL, PRIMARY KEY (follower, followee));
CREATE INDEX IF NOT EXISTS follows_followee ON follows (followee);
CREATE TABLE IF NOT EXISTS notifs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid INTEGER NOT NULL,
  type TEXT NOT NULL,          -- reply | like | follow
  ref TEXT NOT NULL,           -- 댓글 번호 또는 사용자 번호
  slug TEXT NOT NULL DEFAULT '',
  from_nick TEXT NOT NULL DEFAULT '',
  n INTEGER NOT NULL DEFAULT 1,
  updated INTEGER NOT NULL,
  seen INTEGER NOT NULL DEFAULT 0,
  UNIQUE (uid, type, ref)
);
CREATE INDEX IF NOT EXISTS notifs_uid ON notifs (uid, updated);
ALTER TABLE comments ADD COLUMN uid INTEGER;
CREATE INDEX IF NOT EXISTS comments_uid ON comments (uid, created);
