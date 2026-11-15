"""HRTD live update on GitHub: add only what is new. No full rebuild.
1 restore the state (release files named in state/HEAD.json, SHA-256 checked)
2 ask FRED which series changed (series/updates) and pick the held ones whose FRED stamp is newer than ours
3 fetch only rows in force on or after each series' newest held vintage L; the rows in force on L must hash to the stored
  Lhash (else FRED rewrote history: 'problem', nothing added, as update_964 does)
4 add-only rule (rule.add_only; v0 may switch on) -> new points appended to the series' site shard; meta row redone
5 checks: no existing point changed or removed; new points only after the last held one (or v0's); totals never fall
6 aggregate pages rebuilt from the meta rows; changed files only; state saved as a delta; HEAD committed; site deployed
Env: WORK, MAX_MIN (time budget, default 330), CHECK_MIN (save every, default 45), DEPLOY_BRANCH (default 'github' = preview,
'main' = production), DRY=1 (no save, no deploy). Series FRED lists that we do not hold yet are written to new_series.csv."""
import os, sys, json, time, zlib, datetime as dt, traceback
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hrtd import rule, fred, site, store

WORK = os.environ.get('WORK', '/tmp/hrtd_work'); DL = WORK + '_dl'
SITE = f'{WORK}/site/data'; STATE = f'{WORK}/state'
MAX_MIN = float(os.environ.get('MAX_MIN', '330')); CHECK_MIN = float(os.environ.get('CHECK_MIN', '45'))
DRY = os.environ.get('DRY') == '1'
T0 = time.time(); now = lambda: time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
def log(*a): print(now(), *a, flush=True)

class Run:
    def __init__(self):
        self.st = pd.read_parquet(f'{STATE}/series_state.parquet').set_index('series_id')
        self.upd = {}                                       # sid -> changed state fields
        r = pd.read_parquet(f'{STATE}/rows.parquet'); self.rows = dict(zip(r.series_id, (json.loads(x) for x in r.row)))
        ad = pd.read_parquet(f'{STATE}/agency_day.parquet'); co = pd.read_parquet(f'{STATE}/corr.parquet')
        self.maps = {'agency_day': dict(zip(zip(ad.release, ad.day), ad.evidence)),
                     'corr': {(a, b): (c, d) for a, b, c, d in zip(co.release, co.alfred_day, co.real_day, co.text)}}
        sd = pd.read_parquet(f'{STATE}/side.parquet'); self.side = {}
        for x in sd.itertuples(): self.side.setdefault(x.series_id, {})[x.realtime_start] = (x.found, x.release, x.evidence, x.vintage_month, x.source)
        p = pd.read_parquet(f'{STATE}/pop.parquet'); self.pop = dict(zip(p.series_id, p.popularity))
        self.fnames = json.load(open(f'{STATE}/fnames.json'))
        self.shards = {}; self.dirty = set(); self.changed_files = set(); self.log = []
        self.before = {'series': len(self.rows), 'prints': sum(r[12] for r in self.rows.values())}

    def shard(self, k):
        if k not in self.shards: self.shards[k] = json.load(open(f'{SITE}/d/{k}.json'))
        return self.shards[k]

    def get(self, sid, f):
        return self.upd.get(sid, {}).get(f, self.st.at[sid, f])

    def one(self, sid):
        """fetch for one series (thread); returns a result dict for apply()"""
        try:
            status = self.st.at[sid, 'status']; L = self.get(sid, 'L')
            if status not in ('ok', 'no_value') or not L: return {'sid': sid, 'kind': 'skip', 'why': f'state {status}'}
            rows, how = fred.fetch(sid, L)
            if rule.at_L_hash(rows, L) != self.get(sid, 'Lhash'):
                return {'sid': sid, 'kind': 'problem', 'why': f'rows in force on {L} differ from the held ones (FRED changed history)'}
            return {'sid': sid, 'kind': 'fetched', 'rows': rows, 'how': how, 'L': L, 'status': status}
        except Exception as e:
            return {'sid': sid, 'kind': 'error', 'why': f'{type(e).__name__}: {str(e)[:200]}'}

    def apply(self, res, lu):
        sid = res['sid']
        if res['kind'] != 'fetched': self.log.append((now(), sid, res['kind'], res['why'])); return
        rows, L = res['rows'], res['L']
        after = [r for r in rows if r[1] > L]
        newL = max([r[1] for r in rows] + [L])
        if not after:
            self.upd.setdefault(sid, {}).update(fred_lu=lu); self.log.append((now(), sid, 'no_change', '')); return
        rel = self.st.at[sid, 'release']; side = self.side.get(sid, {})
        if res['status'] == 'no_value':                     # nothing valued was held: the whole rule on the new rows
            pts, st2 = rule.full(after, rel, side, self.maps)
            if st2 is None:
                self.upd.setdefault(sid, {}).update(L=newL, Lhash=rule.at_L_hash(rows, newL), fred_lu=lu); self.log.append((now(), sid, 'no_change', 'no value yet')); return
            new_pts = [(d, v, r) for d, v, r, e in pts]; ev = [e for d, v, r, e in pts]; v0_add = None
        else:
            st = {k: self.get(sid, k) for k in ('L', 'M', 'v0', 'd0', 'x0', 'lag0', 'maxlag')}
            for k in ('M', 'v0', 'd0'): st[k] = pd.Timestamp(st[k])
            add, st2 = rule.add_only(st, rule.valued(after))
            days, ev = rule.days_ev(rel, side, self.maps, [a[2] for a in add])
            new_pts = [(a[0], a[1], d) for a, d in zip(add, days)]
            v0_add = None
            if st2['lag0'] <= st2['maxlag'] and not bool(self.get(sid, 'v0_on')):
                d, e = rule.days_ev(rel, side, self.maps, [st['v0'].strftime('%Y-%m-%d')])
                v0_add = (st['d0'].strftime('%Y-%m-%d'), st['x0'], d[0])
        k = zlib.crc32(sid.encode()) % site.NSHARD; sh = self.shard(k)
        if sid not in sh:
            self.log.append((now(), sid, 'needs_record', f'{len(new_pts)} new prints; the series has no site record yet (Mac adds it)')); return
        rec = sh[sid]; old = [list(p) for p in rec['p']]; last = old[-1][0] if old else ''
        add_pts = [site.point(d, v, r) for d, v, r in new_pts]
        if any(p[0] <= last for p in add_pts):
            self.log.append((now(), sid, 'problem', f'a new print is not after the last held one ({last})')); return
        allp = old + add_pts + ([site.point(*v0_add)] if v0_add else [])
        allp.sort(key=lambda p: p[0])
        if len({p[0] for p in allp}) != len(allp): self.log.append((now(), sid, 'problem', 'two prints for one period')); return
        rec['p'] = allp; self.dirty.add(k); self.rows[sid] = site.meta_row(sid, rec)
        u = self.upd.setdefault(sid, {}); u.update(L=newL, Lhash=rule.at_L_hash(rows, newL), fred_lu=lu)
        if res['status'] == 'no_value':
            u.update({kk: st2[kk] for kk in ('M', 'v0', 'd0', 'x0', 'lag0', 'maxlag')}); u.update(status='ok', v0_on=st2['lag0'] <= st2['maxlag'])
        else:
            u.update(M=st2['M'], maxlag=st2['maxlag'], v0_on=bool(self.get(sid, 'v0_on')) or v0_add is not None)
        self.log.append((now(), sid, 'added', f'{len(add_pts)} prints' + (' + first-vintage print' if v0_add else '')))

    def check_and_write(self):
        """write dirty shards after checking every existing point is unchanged; rebuild aggregates"""
        for k in sorted(self.dirty):
            on_disk = json.load(open(f'{SITE}/d/{k}.json'))
            for sid, rec in on_disk.items():
                new = self.shards[k].get(sid)
                if new is None: raise RuntimeError(f'series {sid} would leave shard {k}')
                have = {p[0]: p for p in new['p']}
                for p in rec['p']:
                    if have.get(p[0]) != p: raise RuntimeError(f'{sid}: held print {p} would change to {have.get(p[0])}')
            if site.wjson(f'{SITE}/d/{k}.json', self.shards[k]): self.changed_files.add(f'site/data/d/{k}.json')
        self.dirty.clear()
        before = {p: os.path.getmtime(p) for p in self.agg_files()}
        tot = site.aggregates(list(self.rows.values()), self.pop, self.fnames, json.load(open(f'{SITE}/index.json'))['years'], SITE)
        if tot['series'] < self.before['series'] or tot['prints'] < self.before['prints']:
            raise RuntimeError(f'totals fell: {self.before} -> {tot}')
        for p in self.agg_files():
            if before.get(p) != os.path.getmtime(p): self.changed_files.add(os.path.relpath(p, WORK))
        return tot

    def agg_files(self):
        out = []
        for d in ('m', 'b', 's', 'v'):
            for dp, _, fs in os.walk(f'{SITE}/{d}'): out += [os.path.join(dp, f) for f in fs]
        return out + [f'{SITE}/latest.json', f'{SITE}/index.json']

    def save_state(self):
        st = self.st.copy()
        for sid, u in self.upd.items():
            for f, v in u.items(): st.at[sid, f] = v
        st.reset_index().to_parquet(f'{STATE}/series_state.parquet', index=False)
        pd.DataFrame({'series_id': list(self.rows), 'row': [json.dumps(r, ensure_ascii=False) for r in self.rows.values()]}).to_parquet(f'{STATE}/rows.parquet', index=False)
        self.changed_files |= {'state/series_state.parquet', 'state/rows.parquet'}

def main():
    if os.environ.get('NO_RESTORE') != '1': H = store.restore(WORK, DL); log('state restored:', H.get('updated'))
    R = Run(); log('series held', len(R.st), 'site series', R.before)
    up = fred.updates_list(); log('FRED update list:', len(up))
    have = R.st.index
    lu_new = pd.Series(up); lu_new = lu_new[lu_new.index.isin(have)]
    old = R.st.loc[lu_new.index, 'fred_lu']
    tsn = pd.to_datetime(lu_new, utc=True, errors='coerce', format='mixed'); tso = pd.to_datetime(old, utc=True, errors='coerce', format='mixed')
    # as update_964: a held file written after FRED's stamp already has it (the seed's catalogue stamps are older than the files)
    mt = pd.to_datetime(R.st.loc[lu_new.index, 'src_mtime'], unit='s', utc=True, errors='coerce')
    tso = pd.concat([tso, mt], axis=1).max(axis=1)
    todo = list(lu_new[(tso.isna()) | (tsn > tso)].index)
    pend = f'{STATE}/pending.json'
    if os.path.exists(pend): todo = [s for s in json.load(open(pend)) if s in have] + [s for s in todo if s not in set(json.load(open(pend)))]
    newser = sorted(set(up) - set(have))
    pd.DataFrame({'series_id': newser}).to_csv(f'{STATE}/new_series.csv', index=False)
    log('to update:', len(todo), '| listed by FRED but not held (left to the Mac for now):', len(newser))
    def write_lu(left):                                 # for precheck.py: our FRED stamp of every listed series we hold
        import gzip
        lu = {s: str(R.get(s, 'fred_lu')) for s in up if s in R.st.index}; lu['_pending'] = left
        f = os.environ.get('LU_FILE', '/tmp/hrtd_lu/lu.json.gz'); os.makedirs(os.path.dirname(f), exist_ok=True)
        with gzip.open(f, 'wt') as fh: json.dump(lu, fh)
    def output(k, v):
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as fh: fh.write(f'{k}={v}\n')
    if not todo:
        write_lu(0); output('changed', 'false'); log('nothing new: no save, no deploy'); return
    done = 0; last_save = time.time(); stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    def checkpoint(final):
        nonlocal last_save
        tot = R.check_and_write(); left = todo[done:]
        json.dump(left, open(pend, 'w')); R.changed_files.add('state/pending.json'); R.save_state()
        pd.DataFrame(R.log, columns=['at', 'series_id', 'result', 'note']).to_csv(f'{STATE}/last_run_log.csv', index=False); R.changed_files.add('state/last_run_log.csv')
        if final: write_lu(len(left))
        log('checked:', tot, '| files changed:', len(R.changed_files), '| left:', len(left))
        if not DRY:
            name, size = store.save_delta(WORK, sorted(R.changed_files), time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()), DL)
            store.commit(f'state: {done} series checked, {len(left)} left ({name}, {size >> 20} MB)'); log('saved', name)
            if len(store.head()['order']) > 8:           # keep restores fast: one new base, then the old files go
                parts = store.save_base(WORK, time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()), DL)
                store.commit(f'state: new base {parts}'); store.prune(); log('new base', parts)
            R.changed_files.clear()
        last_save = time.time()
    with ThreadPoolExecutor(int(os.environ.get('FETCH_THREADS', '4'))) as ex:
        it = iter(todo); futs = {}
        for _ in range(16):
            s = next(it, None)
            if s: futs[ex.submit(R.one, s)] = s
        while futs:
            f = next(iter(futs)); s = futs.pop(f); res = f.result()
            R.apply(res, up.get(s, R.get(s, 'fred_lu'))); done += 1   # a series left over from the last run may have left FRED's list
            if (time.time() - T0) / 60 < MAX_MIN:
                s2 = next(it, None)
                if s2: futs[ex.submit(R.one, s2)] = s2
            if done % 500 == 0: log(f'{done}/{len(todo)} | FRED requests {fred.COUNT}')
            if (time.time() - last_save) / 60 > CHECK_MIN: checkpoint(False)
    checkpoint(True)
    kinds = pd.Series([x[2] for x in R.log]).value_counts().to_dict() if R.log else {}
    log('done:', done, 'of', len(todo), kinds)
    output('changed', 'true' if kinds.get('added', 0) else 'false')
    if R.log and kinds.get('error', 0) > max(20, 0.05 * done): raise SystemExit('too many fetch errors: see state/last_run_log.csv')

if __name__ == '__main__':
    main()
