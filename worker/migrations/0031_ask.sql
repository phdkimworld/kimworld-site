-- '이 리포트에 질문하기'(2026-11-11 운영자 지시). 리포트 본문만 근거로 답하는 리포트 도우미
-- 사용량 장부: 하루 합계(질문 수·토큰·추정 달러). 사람 정보 없음, 영구 보관(월 예산 계산과 운영 통계)
CREATE TABLE IF NOT EXISTS ask_usage (
  day TEXT PRIMARY KEY,           -- 한국 날짜 YYYY-MM-DD
  n INTEGER NOT NULL DEFAULT 0,   -- 외부 호출 수(캐시로 답한 것은 제외)
  hits INTEGER NOT NULL DEFAULT 0,-- 캐시로 답한 수
  in_tok INTEGER NOT NULL DEFAULT 0,
  out_tok INTEGER NOT NULL DEFAULT 0,
  cache_w INTEGER NOT NULL DEFAULT 0,
  cache_r INTEGER NOT NULL DEFAULT 0,
  usd REAL NOT NULL DEFAULT 0
);
-- 같은 리포트(같은 본문 판) 같은 질문은 저장한 답을 다시 쓴다. 질문 원문이 들어 있어 30일 뒤 지운다
CREATE TABLE IF NOT EXISTS ask_cache (
  k TEXT PRIMARY KEY,             -- sha256(리포트 판 해시 | 정리한 질문)
  slug TEXT NOT NULL,
  q TEXT NOT NULL,
  answer TEXT NOT NULL,
  created INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ask_cache_created ON ask_cache (created);
-- 질문 기록: 원래 IP는 저장하지 않고 그날만 쓰는 무작위 값으로 만든 해시(ih)만. 30일 뒤 지운다
CREATE TABLE IF NOT EXISTS ask_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created INTEGER NOT NULL,
  day TEXT NOT NULL,
  slug TEXT NOT NULL,
  q TEXT NOT NULL,
  ih TEXT NOT NULL,
  cached INTEGER NOT NULL DEFAULT 0,
  ok INTEGER NOT NULL DEFAULT 1,
  usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ask_log_created ON ask_log (created);
