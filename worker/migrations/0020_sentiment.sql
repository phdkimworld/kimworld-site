-- 0020: 종목 투자 심리 투표(2026-10-14) — 종목 화면 위 '오를 것 같다(불리시) / 내릴 것 같다(베어리시)'
-- · 한 사람(계정, 없으면 기기)·한 종목은 하루 한 표(그날 안에는 바꿀 수 있다). 다음 날 다시 투표 → 매일 참여
-- · 같은 네트워크(그날의 IP 해시)에서 한 종목에 하루 5표까지(통신사 공용 IP는 여러 사람이 같이 쓴다)
-- · sent_daily: 종목·날짜별 합계(그래프와 30일 누적 지수는 여기서 계산). 투표하기 전에는 숫자를 보여 주지 않는다
CREATE TABLE IF NOT EXISTS sent_votes (day TEXT NOT NULL, ticker TEXT NOT NULL, actor TEXT NOT NULL, v INTEGER NOT NULL, ih TEXT NOT NULL, created INTEGER NOT NULL, PRIMARY KEY (day, ticker, actor));
CREATE INDEX IF NOT EXISTS sent_votes_actor ON sent_votes (actor, ticker, day);
CREATE TABLE IF NOT EXISTS sent_daily (ticker TEXT NOT NULL, day TEXT NOT NULL, bull INTEGER NOT NULL DEFAULT 0, bear INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (ticker, day));
