"""1116 test (on the Mac): newseries.new_record() on series the Mac's site already carries must give the Mac's record
(names, units, function, every first-print date and value). Release days are compared too; with empty agency-day tables
they differ only where the Mac holds an agency correction. Usage: python -m tools.test_new [N random series]"""
import sys, os, json, zlib, random
sys.path.insert(0, os.path.expanduser('~/Projects/Onset Detector Data/_shared')); import apikeys
os.environ['FRED_API_KEY'] = apikeys.key('FRED'); os.environ.setdefault('FRED_PER_MIN', '100')
from hrtd import newseries as N, fred
import pandas as pd
C = os.path.expanduser('~/Projects/Onset Detector Data/964_realtime_dataset_blu_2026-10-31/drive_mirror/01_catalog')
c = pd.read_csv(C + '/series.csv', dtype=str, keep_default_na=False, usecols=['series_id', 'release_name', 'agency', 'on_disk'])
c = c[c.on_disk == 'True']; ra = dict(zip(c.release_name, c.agency))
random.seed(7); ids = ['UNRATE', 'ICSA', 'CAUR', 'GDPC1', 'DGS10', 'PAYEMS'] + random.sample(list(c.series_id), int(sys.argv[1]) if len(sys.argv) > 1 else 14)
D = os.path.expanduser('~/Projects/hrtd/deploy/data/d'); same = tot = left = 0
for s in ids:
    k = zlib.crc32(s.encode()) % 2048; mac = json.load(open(f'{D}/{k}.json')).get(s)
    try: out = N.new_record(s, ra, {'agency_day': {}, 'corr': {}})
    except Exception as e: print(s, 'ERR', type(e).__name__, str(e)[:100], flush=True); continue
    if isinstance(out, str): left += 1; print(s, 'LEFT OUT:', out, '| on the Mac site:', mac is not None, flush=True); continue
    rec = out[0]
    if mac is None: print(s, 'not on the Mac site; GitHub would add', len(rec['p']), flush=True); continue
    tot += 1; keys = ('t', 'a', 'r', 'q', 'u', 'sa', 'fn', 'src')
    meta = all(rec[x] == mac[x] for x in keys)
    dv = [(p[0], p[1]) for p in rec['p']] == [(p[0], p[1]) for p in mac['p']]
    days = sum(1 for a, b in zip(rec['p'], mac['p']) if a[2] == b[2]) if dv else -1
    same += meta and dv
    print(s, 'meta', meta, 'dates+values', dv, 'n', len(rec['p']), len(mac['p']), 'release days equal', days,
          '' if meta else {x: (rec[x], mac[x]) for x in keys if rec[x] != mac[x]}, flush=True)
print('equal (meta, dates, values):', same, 'of', tot, '| left out', left, '| FRED requests', fred.COUNT, flush=True)
