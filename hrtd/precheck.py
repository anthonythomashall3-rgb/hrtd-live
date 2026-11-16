"""Cheap check before a full run: is there anything new on FRED for a series we hold?
Compares FRED's update list with lu.json.gz (series_id -> FRED stamp we last handled, kept in the Actions cache and
written by every full run). Writes run=true/false to $GITHUB_OUTPUT. A missing or unreadable lu.json.gz -> run=true."""
import os, sys, json, gzip
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hrtd import fred
LU = os.environ.get('LU_FILE', '/tmp/hrtd_lu/lu.json.gz')
def out(v, why):
    print('run =', v, '|', why, flush=True)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f: f.write(f'run={"true" if v else "false"}\n')
try:
    have = json.load(gzip.open(LU, 'rt'))
except Exception as e:
    out(True, f'no lu.json.gz ({type(e).__name__})'); sys.exit(0)
FRESH = os.environ.get('FRESH_FILE')
if FRESH and os.path.exists(FRESH): os.remove(FRESH)
pend = have.get('_pending', 0)
pl = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'state', 'patches.json')
npatch = len(json.load(open(pl))) if os.path.exists(pl) else 0
if npatch > have.get('_patches', 0): out(True, f'{npatch - have.get("_patches", 0)} history patch(es) from the Mac to apply'); sys.exit(0)
# 1116: FRED lists updates newest first, so only the top of the list is read: down to the stamp the last pass began at
# (one request when nothing is new; the whole list was 119 requests and over a minute). A held series counts whether or not
# it was on the list last time (a quarterly series falls off the two-week list between its releases).
seen = have.get('_seen'); HELD = os.path.dirname(LU) + '/held.txt.gz'
if not seen or not os.path.exists(HELD): out(True, 'no stamp from the last pass: whole list'); sys.exit(0)
held = set(gzip.open(HELD, 'rt').read().split('\n')); ws = pd.Timestamp(seen); fresh = {}; off = 0; top = None; n = 0
while True:
    d = fred.api('series/updates', filter_value='all', limit=1000, offset=off); ss = d.get('seriess', [])
    if not ss: break
    if top is None: top = ss[0]['last_updated']
    newer = [s for s in ss if pd.Timestamp(s['last_updated']) > ws]; n += len(newer)
    fresh.update({s['id']: s['last_updated'] for s in newer if s['id'] in held})
    off += len(ss)
    if len(newer) < len(ss) or off >= int(d.get('count', 0)): break
# 1116: leftovers no longer send the pass through the whole list (119 requests): new stamps and leftovers go together
if (fresh or pend) and FRESH and top: json.dump({'_top': top, 'ids': fresh}, open(FRESH, 'w'))
out(bool(fresh or pend), f'{len(fresh)} held series newer than {seen} ({n} on FRED); {pend} left from the last pass')
