#!/usr/bin/env bash
# 1116 (Anthony 16 Nov 2026: everything on GitHub, the Mac used for nothing in the live updating).
# One job watches FRED for about 5 hours: a check every 30 seconds (one request when nothing is new), and when a held
# series has a newer stamp the add-only update runs at once and the site is deployed. The state stays on the runner's
# disk between passes (restored once per job). When the job ends the workflow starts the next one.
# GitHub's own schedule fired 3 times in 21 hours (asked: every 10 minutes); it is kept only as a second starter.
set -u
END=$((SECONDS + ${WATCH_MIN:-310} * 60))
OUT=$(mktemp); restored=0; need_deploy=0; force="${FORCE:-false}"
git config user.name "hrtd runner"; git config user.email "hrtd@users.noreply.github.com"   # a rebase needs a committer
# 1116 (17 Nov 2026; Anthony: "go"): A FAILING JOB TELLS ANTHONY. On 16 Nov every pass failed for 1 h 46 min and nothing said so.
# After two failed passes in a row: a message to the ntfy topic when the repository has the secret NTFY_TOPIC, and an issue in this
# repository (GitHub mails it and pushes it to the phone app); one open issue at a time, closed by the next pass that succeeds.
fails=0; alerted=0
alert() {
  if [ -n "${NTFY_TOPIC:-}" ]; then curl -fsS -m 15 -H "Title: HRTD update failing" -d "$1" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true; fi
  n=$(gh issue list -R "$GITHUB_REPOSITORY" --state open --search "HRTD update failing in:title" --json number -q '.[0].number' 2>/dev/null)
  if [ -z "$n" ]; then gh issue create -R "$GITHUB_REPOSITORY" --title "HRTD update failing" --body "$1" >/dev/null 2>&1 || true
  else gh issue comment "$n" -R "$GITHUB_REPOSITORY" --body "$1" >/dev/null 2>&1 || true; fi
}
recovered() {
  n=$(gh issue list -R "$GITHUB_REPOSITORY" --state open --search "HRTD update failing in:title" --json number -q '.[0].number' 2>/dev/null)
  if [ -n "$n" ]; then gh issue close "$n" -R "$GITHUB_REPOSITORY" --comment "$1" >/dev/null 2>&1 || true; fi
  if [ -n "${NTFY_TOPIC:-}" ]; then curl -fsS -m 15 -H "Title: HRTD update working again" -d "$1" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true; fi
}
bad() {   # one failed pass; $1 = what failed
  fails=$((fails + 1))
  if [ $fails -ge 2 ] && [ $alerted = 0 ]; then
    alert "hrtd.pages.dev: $fails passes in a row failed ($1) at $(date -u '+%Y-%m-%d %H:%M UTC'). The site keeps its last build. Run: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"; alerted=1
  fi
}
good() { if [ $alerted = 1 ]; then recovered "A pass succeeded at $(date -u '+%Y-%m-%d %H:%M UTC')."; fi; fails=0; alerted=0; }
deploy() {
  D=/mnt/hrtd/deploy; rm -rf "$D"; mkdir -p "$D"
  cp -R web/. "$D/"; cp -al "$WORK/site/data" "$D/data"
  n=$(find "$D" -type f | wc -l); echo "files: $n"
  [ "$n" -lt 19800 ] || { echo "over the Pages limit of 20,000 files"; return 1; }
  npx --yes wrangler@4 pages deploy "$D" --project-name hrtd --branch "$DEPLOY_BRANCH" --commit-dirty=true
}
while [ $SECONDS -lt $END ]; do
  git rebase --abort 2>/dev/null; git reset -q   # nothing half-done or staged is carried into the pull
  git pull -q --rebase origin main || echo "$(date -u +%T) git pull failed (tried again at the next check)"
  : > "$OUT"
  if [ "$force" = true ]; then echo "run=true" > "$OUT"; force=false
  else GITHUB_OUTPUT="$OUT" python -m hrtd.precheck | sed "s/^/$(date -u +%T) /" || echo "check failed"; fi
  if grep -q '^run=true' "$OUT" || { [ $need_deploy = 1 ] && [ $restored = 0 ]; }; then
    # a pass works for at most PASS_MIN minutes (default 5) and then saves and deploys, so during a long backlog a new
    # release is on the site within minutes (new stamps are always fetched first)
    left=$(( (END - SECONDS) / 60 )); [ "$left" -gt "${PASS_MIN:-5}" ] && left="${PASS_MIN:-5}"
    [ "$left" -lt 2 ] && break
    : > "$OUT"
    if [ $restored = 1 ]; then export NO_RESTORE=1; else unset NO_RESTORE; rm -rf "$WORK"; fi
    if GITHUB_OUTPUT="$OUT" MAX_MIN=$left python -m hrtd.update; then restored=1; good
    else echo "$(date -u +%T) update failed: the state is restored from the last saved one at the next pass"; restored=0; bad "the update"; fi
    grep -q '^changed=true' "$OUT" && need_deploy=1
    if [ $need_deploy = 1 ] && [ $restored = 1 ]; then
      if deploy; then need_deploy=0; echo "$(date -u +%T) deployed to $DEPLOY_BRANCH"; else echo "$(date -u +%T) deploy failed: tried again at the next check"; bad "the deploy"; fi
    fi
  elif [ $need_deploy = 1 ]; then
    if deploy; then need_deploy=0; echo "$(date -u +%T) deployed to $DEPLOY_BRANCH"; fi
  fi
  sleep "${WATCH_SLEEP:-30}"
done
echo "$(date -u +%T) watch ends; the next run takes over"
