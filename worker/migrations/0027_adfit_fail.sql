-- 애드핏 알림 중 형식을 못 읽은 글(원인 진단용, 최근 20개, 비공개). 2026-11-01
CREATE TABLE IF NOT EXISTS adfit_fail (id INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL, text TEXT NOT NULL);
