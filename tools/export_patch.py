"""Mac -> GitHub HISTORY PATCH (run on the Mac; launchd daily). The Mac keeps doing the development work that changes history
(stretching series back with scans/HathiTrust/FRASER/other sources, agency-day corrections, removed misreads, new series).
GitHub only adds new releases at the end. This sends GitHub every series whose site record changed in any way that is NOT a
plain append at the end, plus every new series, with its state; and the lookup tables and the calendar when they changed.
Steps (under the Mac's update lock, ~3 min): build the site data from the Mac copy -> compare each series with the baseline
(the last export) -> state of the changed series from their held files. Then pack, upload to the release 'state', list it in
state/patches.json (git), and make this build the new baseline. Usage: python -m tools.export_patch [--dry]"""
import os, sys, json, time, fcntl, glob, hashlib, shutil, tempfile, subprocess, csv
import pandas as pd
ROOT = os.path.expanduser('~/Projects/Onset Detector Data'); W1115 = f'{ROOT}/1115_hrtd_github_2026-11-15'
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (HERE, os.path.expanduser('~/Projects/hrtd'), f'{W1115}/code'): sys.path.insert(0, p)
from hrtd import site, store
BASE = f'{W1115}/patch_baseline'          # the site data and lookup tables as last sent to GitHub
C964 = f'{ROOT}/964_realtime_dataset_blu_2026-10-31'
log = lambda *a: print(time.strftime('%H:%M:%S'), *a, flush=True)

def fhash(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else ''

def main():
    import build_hrtd as B, seed_state_1115 as S, incr_1115 as I
    dry = '--dry' in sys.argv; t0 = time.time()
    tmp = tempfile.mkdtemp(prefix='patch1115_'); new = f'{tmp}/data'
    lk = open(f'{C964}/out/update/update.lock', 'a'); fcntl.flock(lk, fcntl.LOCK_EX); log('lock held')
    try:
        B.fcntl.flock = lambda *a, **k: None; B.OUT = new; B.main(); log('Mac site data built')
        changed, kinds = {}, {'new': 0, 'history': 0, 'meta': 0, 'append_only': 0, 'same': 0}
        for f in sorted(glob.glob(f'{new}/d/*.json')):
            k = os.path.basename(f); a = json.load(open(f)); b = json.load(open(f'{BASE}/d/{k}')) if os.path.exists(f'{BASE}/d/{k}') else {}
            for sid, rec in a.items():
                old = b.get(sid)
                if old is None: changed[sid] = rec; kinds['new'] += 1; continue
                if rec == old: kinds['same'] += 1; continue
                mo = {x: y for x, y in old.items() if x != 'p'}; mn = {x: y for x, y in rec.items() if x != 'p'}
                if rec['p'][:len(old['p'])] == old['p'] and mo == mn: kinds['append_only'] += 1; continue   # GitHub adds these itself
                kinds['history' if rec['p'][:len(old['p'])] != old['p'] else 'meta'] += 1; changed[sid] = rec
        log('series:', kinds)
        cat = pd.read_csv(f'{I.fp.D}/01_catalog/series.csv', dtype=str, keep_default_na=False)
        oth = f'{I.fp.D}/01_catalog/series_other_sources.csv'
        if os.path.exists(oth): cat = pd.concat([cat, pd.read_csv(oth, dtype=str, keep_default_na=False)], ignore_index=True)
        cat = cat[(cat.on_disk == 'True') & (cat.source_file != '')].drop_duplicates('series_id').set_index('series_id')
        jobs = [(s, cat.at[s, 'release_name'], cat.at[s, 'source_file'], cat.at[s, 'last_updated']) for s in changed if s in cat.index]
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(6) as ex: states = pd.DataFrame(list(ex.map(S.one, jobs, chunksize=64))) if jobs else pd.DataFrame()
        I.fp.init(); fp = I.fp
        out = f'{tmp}/patch'; os.makedirs(f'{out}/state')
        ad = pd.DataFrame([(k[0], k[1], v) for k, v in fp.CAT['agency_day'].items()], columns=['release', 'day', 'evidence'])
        co = pd.DataFrame([(k[0], k[1], v[0], v[1]) for k, v in fp.CAT['corr'].items()], columns=['release', 'alfred_day', 'real_day', 'text'])
        side = []
        for sid, r in cat.iterrows():
            src = f'{ROOT}/{r.source_file}'
            if os.path.exists(src[:-len('_all_vintages.csv')] + '_vintage_days.csv'):
                for d, (f, rel, e, vm, n) in fp.other_days(src).items(): side.append((sid, d, f, rel, e, vm, n))
    finally:
        fcntl.flock(lk, fcntl.LOCK_UN); log('lock released')
    import zlib
    if len(states): states['shard'] = [zlib.crc32(x.encode()) % 2048 for x in states.series_id]
    bad = states[~states.status.eq('ok') & ~states.status.eq('no_value')] if len(states) else states
    if len(bad): log('series whose held file could not be read (left out):', len(bad)); changed = {s: r for s, r in changed.items() if s not in set(bad.series_id)}
    states = states[states.series_id.isin(changed)] if len(states) else states
    json.dump(changed, open(f'{out}/records.json', 'w'), separators=(',', ':'), ensure_ascii=False)
    states.to_parquet(f'{out}/state/series_state_patch.parquet', index=False)
    ad.to_parquet(f'{out}/state/agency_day.parquet', index=False); co.to_parquet(f'{out}/state/corr.parquet', index=False)
    pd.DataFrame(side, columns=['series_id', 'realtime_start', 'found', 'release', 'evidence', 'vintage_month', 'source']).to_parquet(f'{out}/state/side.parquet', index=False)
    pd.DataFrame(list(B.load_pop().items()), columns=['series_id', 'popularity']).to_parquet(f'{out}/state/pop.parquet', index=False)
    json.dump({r['folder'][:2]: r['function'] for r in csv.DictReader(open(f'{I.fp.D}/01_catalog/functions.csv', newline='', encoding='utf-8'))}, open(f'{out}/state/fnames.json', 'w'))
    shutil.copytree(f'{new}/cal', f'{out}/cal'); json.dump(json.load(open(f'{new}/index.json'))['years'], open(f'{out}/years.json', 'w'))
    summary = {'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'series': len(changed), **{k: v for k, v in kinds.items()}}
    json.dump(summary, open(f'{out}/summary.json', 'w'))
    log('patch:', summary)
    if dry: log('dry: kept at', out); return out
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()); name = f'patch-{stamp}.tar.zst'; p = f'{tmp}/{name}'
    store.pack(out, sorted(os.listdir(out)), p); h = store.sha(p); store.upload(p)
    subprocess.run(['git', '-C', HERE, 'pull', '-q', '--rebase', 'origin', 'main'], check=True)
    pl = f'{HERE}/state/patches.json'; lst = json.load(open(pl)) if os.path.exists(pl) else []
    lst.append({'name': name, 'sha256': h, **summary}); json.dump(lst, open(pl, 'w'), indent=1)
    subprocess.run(['git', '-C', HERE, 'add', 'state/patches.json'], check=True)
    subprocess.run(['git', '-C', HERE, '-c', 'user.name=Anthony Hall (Mac)', '-c', 'user.email=anthonythomashall3@gmail.com', 'commit', '-qm', f'patch from the Mac: {summary["series"]} series ({name})'], check=True)
    for i in range(5):
        if subprocess.run(['git', '-C', HERE, 'push', '-q', 'origin', 'main']).returncode == 0: break
        subprocess.run(['git', '-C', HERE, 'pull', '-q', '--rebase', 'origin', 'main'], check=True); time.sleep(5)
    else: raise RuntimeError('push failed')
    if os.path.exists(BASE): shutil.rmtree(BASE)
    shutil.copytree(new, BASE)                     # this build is what GitHub now has (plus its own appends)
    mb = os.path.getsize(p) >> 20; shutil.rmtree(tmp, ignore_errors=True)
    log(f'sent {name} ({mb} MB) in {time.time() - t0:.0f}s')

if __name__ == '__main__':
    main()
