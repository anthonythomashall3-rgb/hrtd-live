"""Test of the Mac -> GitHub history patch (on the Mac). In a snapshot copy, 20 series get a STALE history on the GitHub
side (their 3 oldest prints missing, one release day wrong), as if the Mac had since stretched them back and corrected a day.
A patch carrying the Mac's records is applied by hrtd.update (live FRED, nothing saved). Then the 20 must equal the Mac's
records exactly and every other site file must be unchanged. Usage: python -m tools.test_patch SNAP WORKCOPY [make|check]"""
import os, sys, json, random, shutil, glob
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hrtd import site, store
snap, work, step = sys.argv[1], sys.argv[2], sys.argv[3]
P = work + '_patchdir'
if step == 'make':
    rows = pd.read_parquet(f'{snap}/state/rows.parquet'); rnd = random.Random(9)
    pick = []
    for sid in rnd.sample(list(rows.series_id), 4000):
        k = site.shard_of(sid); rec = json.load(open(f'{snap}/site/data/d/{k}.json'))[sid]
        if len(rec['p']) >= 6 and all(p[2] for p in rec['p'][:4]): pick.append(sid)
        if len(pick) == 20: break
    recs = {}
    for sid in pick:
        k = site.shard_of(sid); f = f'{work}/site/data/d/{k}.json'; sh = json.load(open(f))
        recs[sid] = json.load(open(f'{snap}/site/data/d/{k}.json'))[sid]
        stale = [list(p) for p in sh[sid]['p'][3:]]; stale[0][2] = '1999-01-01'      # 3 oldest gone, one day wrong
        sh[sid]['p'] = stale; site.wjson(f, sh)
    r = pd.read_parquet(f'{work}/state/rows.parquet').set_index('series_id')
    for sid in pick:
        k = site.shard_of(sid); r.at[sid, 'row'] = json.dumps(site.meta_row(sid, json.load(open(f'{work}/site/data/d/{k}.json'))[sid]), ensure_ascii=False)
    r.reset_index().to_parquet(f'{work}/state/rows.parquet', index=False)
    if os.path.exists(P): shutil.rmtree(P)
    out = f'{P}/build'; os.makedirs(f'{out}/state')
    json.dump(recs, open(f'{out}/records.json', 'w'), separators=(',', ':'), ensure_ascii=False)
    st = pd.read_parquet(f'{snap}/state/series_state.parquet'); st[st.series_id.isin(pick)].to_parquet(f'{out}/state/series_state_patch.parquet', index=False)
    for f in ('agency_day.parquet', 'corr.parquet', 'side.parquet', 'pop.parquet', 'fnames.json'): shutil.copy(f'{snap}/state/{f}', f'{out}/state/{f}')
    shutil.copytree(f'{snap}/site/data/cal', f'{out}/cal'); json.dump(json.load(open(f'{snap}/site/data/index.json'))['years'], open(f'{out}/years.json', 'w'))
    name = 'patch-test.tar.zst'; store.pack(out, sorted(os.listdir(out)), f'{P}/{name}')
    json.dump([{'name': name, 'sha256': store.sha(f'{P}/{name}'), 'series': len(pick)}], open(f'{P}/patches.json', 'w'))
    json.dump(pick, open(f'{P}/picked.json', 'w')); print('stale history made for', len(pick), 'series; patch', name)
else:
    pick = json.load(open(f'{P}/picked.json')); ok = 0
    for sid in pick:
        k = site.shard_of(sid)
        a = json.load(open(f'{snap}/site/data/d/{k}.json'))[sid]; b = json.load(open(f'{work}/site/data/d/{k}.json'))[sid]
        if a == b: ok += 1
        else: print('DIFF', sid, len(a['p']), len(b['p']))
    other = 0
    for p in glob.glob(f'{work}/site/data/**/*.json', recursive=True):
        rel = os.path.relpath(p, f'{work}/site/data')
        if rel.startswith(('s/', 'v/')) or rel == 'index.json': continue
        if open(p, 'rb').read() != open(f'{snap}/site/data/{rel}', 'rb').read(): other += 1
    print(f'patched series equal to the Mac: {ok}/{len(pick)} | site files (outside search) different from the Mac snapshot: {other}')
