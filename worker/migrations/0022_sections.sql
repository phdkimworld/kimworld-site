-- 리포트 구간별 도달·체류(2026-10-21 운영자 지시 '리포트 독자 반응을 보고 체류시간 극대화'): 날짜·리포트·구간 코드별 합계
-- sec: top(핵심 요약 등 첫 구간) ans(짧은 답) can(이 리포트에서) news(같은 뉴스) term(용어) p1~p6(1~6부) src(출처) more(다음 리포트) comm(이야기)
CREATE TABLE IF NOT EXISTS an_sec (day TEXT NOT NULL, path TEXT NOT NULL, sec TEXT NOT NULL, reach INTEGER NOT NULL DEFAULT 0, secs INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, path, sec));
