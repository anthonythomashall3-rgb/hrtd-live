# HRTD live (hrtd.pages.dev), run on GitHub

HRTD (Hall Realtime Database) publishes every U.S. series' **first print** (first published value of each period) and the
day it was released. This repository keeps it current with no Mac and no drive: GitHub Actions asks FRED what changed,
fetches only the new rows, adds only the new first prints, and deploys the site to Cloudflare Pages.

## How a run works (`hrtd/update.py`)
1. **Check** (`precheck.py`, every 10 minutes): does FRED list any series we hold with a newer stamp? If not, stop.
2. **Restore** the state from this repo's release `state` (a base snapshot + deltas, each checked by SHA-256 against `state/HEAD.json`).
3. **Fetch only what is new**: for each changed series, the rows in force on or after its newest held vintage `L`.
   The rows in force on `L` must match the stored hash, or FRED has rewritten history: the series is marked `problem`
   and nothing is added (the same refusal as the Mac's update).
4. **Add only**: the first-print rule (`rule.py`, a port of the Mac's `first_prints_964.one()`) applied to the new vintages
   from a small per-series state (`L`, newest period `M`, first vintage `v0`, lags). No full rebuild.
5. **Check**: no held print may change or disappear; new prints only after the last held one; totals never fall.
6. **Save** the changed files as a delta and commit `state/HEAD.json` (a run that dies before this leaves the old state whole);
   **deploy** (only changed files upload).

## Tested before use (on the Mac, 15 Nov 2026)
- Add-only vs the full rebuild: 9,832 series (random + every multi-source series + the 400 largest files): 0 differences.
- This repo's `rule.py` vs the Mac's real code: 6,999 hard cases: 0 differences.
- New-rows-only fetch vs held files: identical except D9POP and D12POP, which FRED rewrote; the history guard flags exactly those.
- `site.py` vs the Mac's site: all 676,326 series, 32,202,426 prints; every page identical in content
  (the Mac's search files vary in order from run to run; this repo writes them in sorted order).

## Shadow weeks
`DEPLOY_BRANCH: github` publishes to the preview `github.hrtd.pages.dev`, and `parity.py` compares every changed series
with the Mac's live site (`parity/*.jsonl`: same / ahead / behind / CONFLICT). The switch to `main` (hrtd.pages.dev itself)
comes after 7 days with 0 conflicts.

## Secrets
`FRED_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `BLS_API_KEY` (GitHub secrets; never printed).
