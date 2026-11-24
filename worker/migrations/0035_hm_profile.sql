-- 건강몰 시청자 프로필별 방문·전환(운영자 2026-11-24 "컨텐츠별로 타겟 독자층 프로필을 링크에 태그해서 프로필별로 방문 및 구매전환을 추적").
-- 프로필(prof)은 사람이 아니라 '들어온 링크(영상)'의 관심 분야 코드다: 링크의 aud= 값, 없으면 utm_campaign(영상 slug)을 health.yaml profile_map 으로 바꾼 값, 모르면 '-'.
-- 날짜별 합계만, 개인 식별값 없음(hm_* 와 같음). camp = utm_campaign[.utm_medium] (영상·자리별).
CREATE TABLE IF NOT EXISTS hm_prof (day TEXT NOT NULL, site TEXT NOT NULL, prof TEXT NOT NULL, camp TEXT NOT NULL,
  sess INTEGER NOT NULL DEFAULT 0, pv INTEGER NOT NULL DEFAULT 0, secs INTEGER NOT NULL DEFAULT 0, engaged INTEGER NOT NULL DEFAULT 0,
  deep INTEGER NOT NULL DEFAULT 0, coupang INTEGER NOT NULL DEFAULT 0, ui INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, site, prof, camp));
-- 프로필별 행동: kind = coupang(sub = 진열 자리) · guide · youtube · ui(sub = 프로필 상자·자가 점검·정렬 버튼 등 화면 안 행동)
CREATE TABLE IF NOT EXISTS hm_prof_ev (day TEXT NOT NULL, site TEXT NOT NULL, prof TEXT NOT NULL, kind TEXT NOT NULL, sub TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, site, prof, kind, sub));
