-- 애드핏 전달 앱 열쇠(운영 통계 화면에서 운영자가 만든다). 열쇠 원문은 저장하지 않고 SHA-256만
CREATE TABLE IF NOT EXISTS adfit_keys (
  sha TEXT PRIMARY KEY,
  created INTEGER NOT NULL
);
