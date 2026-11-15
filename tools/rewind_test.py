"""End-to-end test (run on the Mac against a snapshot copy): rewind N series that FRED updated recently by 1-4 vintages
(state and site record as they were then, from the Mac's held file cut at that vintage), run hrtd.update with live FRED,
then every rewound series must hold again exactly the prints of the untouched snapshot (newer ones allowed only after them).
Usage: python -m tools.rewind_test SNAPCOPY ORIGINAL_SNAP N"""
import os, sys, json, random, zlib, glob
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hrtd import rule, site
ROOT = os.path.expanduser('~/Projects/Onset Detector Data')
work, orig, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
mode = sys.argv[4] if len(sys.argv) > 4 else 'rewind'
st = pd.read_parquet(f'{work}/state/series_state.parquet').set_index('series_id')
if mode == 'rewind':
    up = pd.read_csv(sorted(glob.glob(f'{ROOT}/964_realtime_dataset_blu_2026-10-31/out/update/fred_updates_*.csv'))[-1], dtype=str)
    rows_meta = pd.read_parquet(f'{work}/state/rows.parquet'); have_rec = set(rows_meta.series_id)
    ad = pd.read_parquet(f'{work}/state/agency_day.parquet'); co = pd.read_parquet(f'{work}/state/corr.parquet')
    maps = {'agency_day': dict(zip(zip(ad.release, ad.day), ad.evidence)), 'corr': {(a, b): (c, d) for a, b, c, d in zip(co.release, co.alfred_day, co.real_day, co.text)}}
    cand = [s for s in up.series_id if s in st.index and s in have_rec and 'alfred' in st.at[s, 'src_rel']]
    random.Random(5).shuffle(cand); picked = []
    for s in cand:
        if len(picked) >= n: break
        rows = [tuple(r) for r in pd.read_csv(f'{ROOT}/{st.at[s, "src_rel"]}', dtype=str, keep_default_na=False).itertuples(index=False)]
        vint = sorted({r[1] for r in rows})
        if len(vint) < 6: continue
        c = vint[-1 - random.Random(s).randint(1, 4)]
        cut = [r for r in rows if r[1] <= c]
        pts, st2 = rule.full(cut, st.at[s, 'release'], {}, maps)
        if st2 is None or not pts: continue
        k = site.shard_of(s); shard = json.load(open(f'{work}/site/data/d/{k}.json'))
        full_now = [p[0] for p in shard[s]['p']]
        cut_pts = [site.point(d, v, r) for d, v, r, e in pts]
        if [p[0] for p in cut_pts] != full_now[:len(cut_pts)] or len(cut_pts) == len(full_now): continue   # only series whose newer prints come after
        shard[s]['p'] = cut_pts; site.wjson(f'{work}/site/data/d/{k}.json', shard)
        for f in ('L', 'M', 'v0', 'd0', 'x0', 'lag0', 'maxlag', 'Lhash'): st.at[s, f] = st2[f]
        st.at[s, 'v0_on'] = st2['lag0'] <= st2['maxlag']; st.at[s, 'fred_lu'] = '1900-01-01'; st.at[s, 'src_mtime'] = 0.0
        picked.append((s, c, len(full_now) - len(cut_pts)))
    st.reset_index().to_parquet(f'{work}/state/series_state.parquet', index=False)
    rm = rows_meta.set_index('series_id')
    for s, _, _ in picked:
        k = site.shard_of(s); rec = json.load(open(f'{work}/site/data/d/{k}.json'))[s]; rm.at[s, 'row'] = json.dumps(site.meta_row(s, rec), ensure_ascii=False)
    rm.reset_index().to_parquet(f'{work}/state/rows.parquet', index=False)
    json.dump(picked, open(f'{work}/rewound.json', 'w')); print('rewound', len(picked), 'series; prints removed:', sum(p[2] for p in picked))
else:   # check
    picked = json.load(open(f'{work}/rewound.json')); res = {'same': 0, 'ahead_ok': 0, 'DIFF': 0}
    for s, c, nrm in picked:
        k = site.shard_of(s)
        a = json.load(open(f'{orig}/site/data/d/{k}.json'))[s]['p']; b = json.load(open(f'{work}/site/data/d/{k}.json'))[s]['p']
        if a == b: res['same'] += 1
        elif b[:len(a)] == a: res['ahead_ok'] += 1
        else:
            res['DIFF'] += 1; i = next((j for j, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            print('DIFF', s, 'cut', c, 'mac', a[i:i + 1], 'github', b[i:i + 1], len(a), len(b))
    print(res)
