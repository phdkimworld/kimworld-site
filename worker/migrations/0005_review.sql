-- 자동 검토: 이미 검토한 글은 다시 대기열에 올리지 않는다
ALTER TABLE comments ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS comments_review ON comments (reviewed, status);
