-- 종목 리포트 업데이트 요청(2026-10-21 운영자 요청): 한 사람(계정, 없으면 기기)·한 종목 하나. 최근 30일 요청만 센다
CREATE TABLE IF NOT EXISTS upd_req (ticker TEXT NOT NULL, actor TEXT NOT NULL, ih TEXT NOT NULL, created INTEGER NOT NULL, PRIMARY KEY (ticker, actor));
CREATE INDEX IF NOT EXISTS upd_req_recent ON upd_req (created, ticker);
