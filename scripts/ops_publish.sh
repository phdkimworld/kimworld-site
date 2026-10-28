#!/usr/bin/env bash
# 운영 통계 JSON을 비공개 저장소(phdkimworld/kimworld, ops-data 브랜치 stats/<이름>.json)에 올린다. 2026-10-28 운영자 요청 "운영통계는 더 비공개로".
# 사용: scripts/ops_publish.sh <파일.json> <이름>
# 필요한 비밀값: OPS_PUSH_TOKEN (fine-grained 토큰, phdkimworld/kimworld 저장소 Contents: Read and write 만). 없으면 0이 아닌 값(3)으로 끝나고, 부른 쪽이 예전 방식(공개 주석, 수익 숫자 뺌)으로 대신한다.
set -euo pipefail
SRC="$1"; NAME="$2"
if [ -z "${OPS_PUSH_TOKEN:-}" ]; then echo "::notice title=OPS::비공개 저장소 토큰 없음 — 공개 주석(수익 제외)으로 대신"; exit 3; fi
echo "::add-mask::$OPS_PUSH_TOKEN"
D=$(mktemp -d)
git clone -q --depth 1 -b ops-data "https://x-access-token:${OPS_PUSH_TOKEN}@github.com/phdkimworld/kimworld.git" "$D" 2>/dev/null || { echo "::warning title=OPS::비공개 저장소 받기 실패(토큰 권한 확인)"; exit 3; }
mkdir -p "$D/stats"
cp "$SRC" "$D/stats/$NAME.json"
cd "$D"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add "stats/$NAME.json"
if git diff --cached --quiet; then echo "::notice title=OPS::$NAME 바뀐 것 없음"; exit 0; fi
git commit -q -m "$NAME $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M') KST"
for i in 1 2 3 4; do git pull -q --rebase origin ops-data && git push -q origin HEAD:ops-data && { echo "::notice title=OPS::$NAME → 비공개 저장소 stats/$NAME.json"; exit 0; }; sleep $((i * 5)); done
exit 1
