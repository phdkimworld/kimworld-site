-- 애드핏 데일리 리포트(운영자 휴대폰이 카카오톡 알림을 그대로 보내 줌, 2026-10-28). 한국 날짜 하루 한 줄
CREATE TABLE IF NOT EXISTS adfit_daily (
  day TEXT PRIMARY KEY,
  earn INTEGER, requests INTEGER, impressions INTEGER, rendered INTEGER, clicks INTEGER, ecpm INTEGER,
  cum_earn INTEGER, confirmed INTEGER,
  updated INTEGER NOT NULL
);
