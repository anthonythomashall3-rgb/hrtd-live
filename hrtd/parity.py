"""Side by side with the Mac (shadow weeks): every series this run added prints to is compared with the same series on the
live site the Mac publishes (https://hrtd.pages.dev/data/d/<shard>.json). For each series:
  same      both hold exactly the same prints
  ahead     GitHub holds newer prints the Mac has not published yet (every shared print equal)
  behind    the Mac holds newer prints (every shared print equal)
  CONFLICT  a period both hold with a different value or release day -> must be 0 before the switch
Appends one line per run to parity/<YYYY-MM>.jsonl (committed with the state)."""
import os, sys, json, time, zlib, urllib.request
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hrtd import site
WORK = os.environ.get('WORK', '/tmp/hrtd_work'); HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get('PROD_URL', 'https://hrtd.pages.dev')

def main():
    lg = pd.read_csv(f'{WORK}/state/last_run_log.csv', dtype=str)
    ids = sorted(set(lg[lg.result == 'added'].series_id))
    res = {'same': 0, 'ahead': 0, 'behind': 0, 'CONFLICT': 0, 'missing_on_site': 0}; conflicts = []
    by = {}
    for s in ids: by.setdefault(site.shard_of(s), []).append(s)
    for k, sids in by.items():
        mine = json.load(open(f'{WORK}/site/data/d/{k}.json'))
        try:
            with urllib.request.urlopen(urllib.request.Request(f'{BASE}/data/d/{k}.json', headers={'User-Agent': 'hrtd-parity'}), timeout=60) as r: theirs = json.loads(r.read())
        except Exception as e:
            res['missing_on_site'] += len(sids); continue
        for s in sids:
            a = {p[0]: p for p in mine[s]['p']}; b = {p[0]: p for p in theirs.get(s, {'p': []})['p']}
            bad = [d for d in set(a) & set(b) if a[d] != b[d]]
            if bad: res['CONFLICT'] += 1; conflicts.append([s, a[bad[0]], b[bad[0]]])
            elif set(a) == set(b): res['same'] += 1
            elif set(b) < set(a): res['ahead'] += 1
            else: res['behind'] += 1
    line = {'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'series': len(ids), **res, 'conflicts': conflicts[:20]}
    os.makedirs(f'{HERE}/parity', exist_ok=True)
    with open(f'{HERE}/parity/{time.strftime("%Y-%m")}.jsonl', 'a') as f: f.write(json.dumps(line) + '\n')
    print(json.dumps(line), flush=True)
    if res['CONFLICT']: sys.exit(2)

if __name__ == '__main__':
    main()
