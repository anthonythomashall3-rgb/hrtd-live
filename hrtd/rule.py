"""The first-print rule, self-contained (no Mac code needed). A line-for-line port of 964/code/first_prints_964.py one(),
plus the ADD-ONLY update tested against it on the Mac (1115: 9,832 series, 0 differences).

First print of period d = its earliest published value (earliest realtime_start with a value). It counts only if d was NEW
when it appeared: later than every period published before that day. In the first vintage only its newest period counts,
and only if its lag is within the lags of the series' later first prints.
Rows everywhere: (date, realtime_start, realtime_end, value) as ALFRED strings; '.' = no value."""
import hashlib
import pandas as pd, pyarrow as pa, pyarrow.compute as pcp

ALFRED_EV = 'ALFRED vintage date (not yet checked against the agency record)'

def valued(rows):
    """one()'s parse: value string -> float64 by Arrow ('.' -> none); valued rows only, sorted by (realtime_start, date)"""
    if not rows: return pd.DataFrame({'date': pd.Series(dtype='datetime64[ns]'), 'realtime_start': pd.Series(dtype='datetime64[ns]'), 'value': pd.Series(dtype=float)})
    d, s, _, v = zip(*rows)
    v = pa.array(v, pa.string()); v = pcp.if_else(pcp.equal(v, '.'), pa.scalar(None, pa.string()), v).cast(pa.float64())
    t = pd.DataFrame({'date': list(d), 'realtime_start': list(s), 'value': v.to_pandas()})
    t = t[t.value.notna()].copy()
    t['date'] = pd.to_datetime(t.date); t['realtime_start'] = pd.to_datetime(t.realtime_start)
    return t.sort_values(['realtime_start', 'date'])

def at_L_hash(rows, L):
    """rows in force on day L as (date, value). Held: start <= L <= end. A fetch from L returns them cut at L."""
    x = sorted((r[0], r[3]) for r in rows if r[1] <= L <= r[2])
    return hashlib.sha256('\n'.join(f'{a},{b}' for a, b in x).encode()).hexdigest()

def days_ev(rel, side, maps, starts):
    """release day + evidence of each vintage day; same order of records as one(): other source, agency correction,
    agency day, else the ALFRED day. side: {realtime_start: (found, release, evidence, vintage_month, source_name)}"""
    days, ev = [], []
    for d in starts:
        if d in side:
            f, r, e, vm, sname = side[d]
            if f == '1': days.append(d); ev.append(f'{sname}: {e}')
            else: days.append(None); ev.append(f'release day not yet found: {sname} vintage {vm}, held as of {d} (not a release day; 99_build/vintage_days_to_find.csv)')
        elif (rel, d) in maps['corr']: x = maps['corr'][(rel, d)]; days.append(x[0]); ev.append(x[1])
        elif (rel, d) in maps['agency_day']: days.append(d); ev.append(maps['agency_day'][(rel, d)])
        else: days.append(d); ev.append(ALFRED_EV)
    return days, ev

def full(rows, rel, side, maps):
    """one() on a whole series: -> (list of (date 'YYYY-MM-DD', value float, release_date or None, evidence), state or None)"""
    t = valued(rows)
    if t.empty: return [], None
    first = t.drop_duplicates('date', keep='first')
    vmax = t.groupby('realtime_start').date.max()
    prior = vmax.cummax().shift(1)
    v0 = vmax.index[0]; d0 = t[t.realtime_start == v0].date
    older = d0[d0 < d0.max()]
    prior.iloc[0] = older.max() if len(older) else pd.NaT
    pm = first.realtime_start.map(prior)
    ok = first[pm.isna() | (first.date > pm)]
    lag = (ok.realtime_start - ok.date).dt.days
    later = lag[ok.realtime_start > v0]
    in_v0 = ok.realtime_start == v0
    ok = ok[~in_v0 | (lag <= (later.max() if len(later) else -1))]
    st = state_from(t, max(r[1] for r in rows))
    st['Lhash'] = at_L_hash(rows, st['L'])
    if ok.empty: return [], st
    days, ev = days_ev(rel, side, maps, list(ok.realtime_start.dt.strftime('%Y-%m-%d')))
    return [(d.strftime('%Y-%m-%d'), float(v), dd, e) for d, v, dd, e in zip(ok.date, ok.value, days, ev)], st

def state_from(t, L):
    """state after valued rows t (sorted). L = newest realtime_start of ALL held rows."""
    if t.empty: return None
    v0 = t.realtime_start.iloc[0]; d0 = t[t.realtime_start == v0]; d0max = d0.date.max()
    first = t.drop_duplicates('date', keep='first')
    vmax = t.groupby('realtime_start').date.max(); prior = vmax.cummax().shift(1)
    older = d0.date[d0.date < d0max]; prior.iloc[0] = older.max() if len(older) else pd.NaT
    pm = first.realtime_start.map(prior); ok = first[pm.isna() | (first.date > pm)]
    lag = (ok.realtime_start - ok.date).dt.days; later = lag[ok.realtime_start > v0]
    return {'L': L, 'M': vmax.max(), 'v0': v0, 'd0': d0max, 'x0': float(d0[d0.date == d0max].value.iloc[0]),
            'lag0': int((v0 - d0max).days), 'maxlag': int(later.max()) if len(later) else -1}

def add_only(st, new):
    """st: state; new: valued rows with realtime_start > L (sorted). -> (list of (date, value, vintage day), new state).
    v0's period counts iff new_state lag0 <= maxlag (it can only switch ON: maxlag never falls)."""
    st = dict(st); out = []
    for v, g in new.groupby('realtime_start', sort=True):
        g = g.drop_duplicates('date', keep='first')
        for r in g[g.date > st['M']].itertuples():
            out.append((r.date.strftime('%Y-%m-%d'), float(r.value), v.strftime('%Y-%m-%d'))); st['maxlag'] = max(st['maxlag'], int((v - r.date).days))
        st['M'] = max(st['M'], g.date.max())
    return out, st
