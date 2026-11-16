#!/usr/bin/env bash
# 1116 (Anthony 16 Nov 2026: everything on GitHub, the Mac used for nothing in the live updating).
# One job watches FRED for about 5 hours: a check every 30 seconds (one request when nothing is new), and when a held
# series has a newer stamp the add-only update runs at once and the site is deployed. The state stays on the runner's
# disk between passes (restored once per job). When the job ends the workflow starts the next one.
# GitHub's own schedule fired 3 times in 21 hours (asked: every 10 minutes); it is kept only as a second starter.
set -u
END=$((SECONDS + ${WATCH_MIN:-310} * 60))
OUT=$(mktemp); restored=0; need_deploy=0; force="${FORCE:-false}"
deploy() {
  D=/mnt/hrtd/deploy; rm -rf "$D"; mkdir -p "$D"
  cp -R web/. "$D/"; cp -al "$WORK/site/data" "$D/data"
  n=$(find "$D" -type f | wc -l); echo "files: $n"
  [ "$n" -lt 19800 ] || { echo "over the Pages limit of 20,000 files"; return 1; }
  npx --yes wrangler@4 pages deploy "$D" --project-name hrtd --branch "$DEPLOY_BRANCH" --commit-dirty=true
}
while [ $SECONDS -lt $END ]; do
  git pull -q --rebase origin main || echo "$(date -u +%T) git pull failed (tried again at the next check)"
  : > "$OUT"
  if [ "$force" = true ]; then echo "run=true" > "$OUT"; force=false
  else GITHUB_OUTPUT="$OUT" python -m hrtd.precheck | sed "s/^/$(date -u +%T) /" || echo "check failed"; fi
  if grep -q '^run=true' "$OUT" || { [ $need_deploy = 1 ] && [ $restored = 0 ]; }; then
    left=$(( (END - SECONDS) / 60 )); [ "$left" -gt 25 ] && left=25
    [ "$left" -lt 2 ] && break
    : > "$OUT"
    if [ $restored = 1 ]; then export NO_RESTORE=1; else unset NO_RESTORE; rm -rf "$WORK"; fi
    if GITHUB_OUTPUT="$OUT" MAX_MIN=$left python -m hrtd.update; then restored=1
    else echo "$(date -u +%T) update failed: the state is restored from the last saved one at the next pass"; restored=0; fi
    grep -q '^changed=true' "$OUT" && need_deploy=1
    if [ $need_deploy = 1 ] && [ $restored = 1 ]; then
      if deploy; then need_deploy=0; echo "$(date -u +%T) deployed to $DEPLOY_BRANCH"; else echo "$(date -u +%T) deploy failed: tried again at the next check"; fi
    fi
  elif [ $need_deploy = 1 ]; then
    if deploy; then need_deploy=0; echo "$(date -u +%T) deployed to $DEPLOY_BRANCH"; fi
  fi
  sleep "${WATCH_SLEEP:-30}"
done
echo "$(date -u +%T) watch ends; the next run takes over"
