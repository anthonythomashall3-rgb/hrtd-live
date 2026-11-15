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
up = fred.updates_list()
pend = have.get('_pending', 0)
pl = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'state', 'patches.json')
npatch = len(json.load(open(pl))) if os.path.exists(pl) else 0
if npatch > have.get('_patches', 0): out(True, f'{npatch - have.get("_patches", 0)} history patch(es) from the Mac to apply'); sys.exit(0)
if pend: out(True, f'{pend} series left from the last run'); sys.exit(0)
new = [s for s, lu in up.items() if s in have and pd.Timestamp(lu) > pd.Timestamp(have[s])]
out(bool(new), f'{len(new)} held series with a newer FRED stamp (of {len(up)} listed)')
