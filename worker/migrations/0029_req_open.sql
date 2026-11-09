-- 종목별 업데이트 요청 기준 시각(최신 리포트 공개일 0시 ET, 밀리초). 사이트 배포(deploy.yml Board notices)가 dist/req-open.json 으로 채운다(2026-11-08)
CREATE TABLE IF NOT EXISTS req_open (ticker TEXT PRIMARY KEY, opens INTEGER NOT NULL);
