-- 리포트 좋아요(같은 사람은 글마다 한 번), 답글(한 단계)
CREATE TABLE IF NOT EXISTS post_likes (slug TEXT NOT NULL, ih TEXT NOT NULL, created INTEGER NOT NULL, PRIMARY KEY (slug, ih));
CREATE TABLE IF NOT EXISTS likes_total (slug TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0);
ALTER TABLE comments ADD COLUMN parent_id INTEGER;
CREATE INDEX IF NOT EXISTS comments_parent ON comments (parent_id);
