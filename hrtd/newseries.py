"""1116 (Anthony 16 Nov 2026: everything on GitHub). A series FRED lists that HRTD does not hold yet is added here, no Mac:
kept only when it is plainly a U.S. series of a release HRTD already carries -
  1 its release is one we hold (the agency is that release's agency);
  2 FRED tags it 'usa' or with a U.S.-only geography type (state, county, msa, ...) and with no foreign country tag
    (the Mac's catalogue rule, 964/code/alfred_list_964.py, applied to the one series; a series with no U.S. tag is left out);
then its whole ALFRED record is fetched and the first-print rule (rule.full) run on it; the function comes from the Mac's
written rules (functions.py). Anything else is written to state/new_rejects.json with the reason and not asked again
until FRED stamps it anew ('not U.S.' is never asked again)."""
import os, json, time, zlib
from hrtd import fred, rule, site, functions as F

USGEOT = {'state', 'county', 'msa', 'metropolitan division', 'necta', 'census region', 'census division', 'bea region',
          'frb district', 'micropolitan', 'csa', 'city', 'censustract', 'zip code'}
FOREIGN = set(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'foreign_geo_tags.json'))))
START = '1776-07-04'

def new_record(sid, rel_agency, maps):
    """-> (record, state row, popularity) or a string (why it is left out; 'not U.S.' is final)"""
    tags = {t['name'] for t in fred.api('series/tags', series_id=sid).get('tags', [])}
    if not ('usa' in tags or tags & USGEOT) or (tags & FOREIGN and 'usa' not in tags): return 'not U.S. by FRED tags'
    rels = fred.api('series/release', series_id=sid).get('releases', [])
    if not rels or rels[0]['name'] not in rel_agency: return 'release not held: ' + (rels[0]['name'] if rels else 'none')
    rel = rels[0]['name']
    m = fred.api('series', series_id=sid)['seriess'][0]
    rows, how = fred.fetch(sid, START); rows.sort()
    pts, st = rule.full(rows, rel, {}, maps)
    if st is None or not pts: return 'no first print yet'
    pts.sort(key=lambda p: p[0])
    rec = {'t': m.get('title', sid), 'a': rel_agency[rel], 'r': rel, 'q': m.get('frequency', ''), 'u': m.get('units', ''),
           'sa': m.get('seasonal_adjustment', ''), 'fn': F.NUM[F.classify(m.get('title', ''), rel)[0]], 'src': '',
           'p': [site.point(d, v, dd) for d, v, dd, e in pts]}
    row = {'release': rel, 'src_rel': '', 'fred_lu': m.get('last_updated', ''), 'src_mtime': time.time(), 'L': st['L'], 'Lhash': st['Lhash'],
           'M': st['M'], 'v0': st['v0'], 'd0': st['d0'], 'x0': st['x0'], 'lag0': st['lag0'], 'maxlag': st['maxlag'],
           'v0_on': st['lag0'] <= st['maxlag'], 'status': 'ok', 'shard': zlib.crc32(sid.encode()) % site.NSHARD}
    return rec, row, int(m.get('popularity') or 0)
