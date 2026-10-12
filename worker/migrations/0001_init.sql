-- 김박사 월드 API(조회수·댓글·좋아요·검색어) 저장소. 원래 IP는 저장하지 않고 비밀 소금으로 만든 해시(ih)만 남긴다.
CREATE TABLE IF NOT EXISTS views_total (slug TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS views_daily (slug TEXT NOT NULL, day TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (slug, day));
CREATE TABLE IF NOT EXISTS view_seen (day TEXT NOT NULL, slug TEXT NOT NULL, ih TEXT NOT NULL, PRIMARY KEY (day, slug, ih));
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL,
  nick TEXT NOT NULL,
  body TEXT NOT NULL,
  ih TEXT NOT NULL,
  created INTEGER NOT NULL,
  likes INTEGER NOT NULL DEFAULT 0,
  reports INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ok'   -- ok | held(자동 보류) | hidden(신고 누적) | deleted
);
CREATE INDEX IF NOT EXISTS comments_slug ON comments (slug, status, created);
CREATE INDEX IF NOT EXISTS comments_ih ON comments (ih, created);
CREATE TABLE IF NOT EXISTS comment_likes (cid INTEGER NOT NULL, ih TEXT NOT NULL, PRIMARY KEY (cid, ih));
CREATE TABLE IF NOT EXISTS comment_reports (cid INTEGER NOT NULL, ih TEXT NOT NULL, PRIMARY KEY (cid, ih));
CREATE TABLE IF NOT EXISTS searches (day TEXT NOT NULL, q TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, q));
CREATE TABLE IF NOT EXISTS search_seen (day TEXT NOT NULL, q TEXT NOT NULL, ih TEXT NOT NULL, PRIMARY KEY (day, q, ih));
