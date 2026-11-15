"""FRED/ALFRED access for the GitHub run: a port of 964/code/update_964.py api/obs/windowed/fetch/updates_list.
Key from the environment (FRED_API_KEY); never printed. A global pace (FRED_PER_MIN, default 60) keeps us under
FRED's 120 requests a minute per key; HTTP 429/5xx and network errors wait and retry (40 tries), as on the Mac."""
import os, re, json, time, threading, urllib.parse, urllib.request, urllib.error, datetime as dt

KEY = os.environ.get('FRED_API_KEY', '')
BASE = 'https://api.stlouisfed.org/fred/'
PER_MIN = float(os.environ.get('FRED_PER_MIN', '60'))
_lock = threading.Lock(); _next = [0.0]
COUNT = {'requests': 0, 'retries': 0}

def _pace():
    with _lock:
        now = time.monotonic(); wait = _next[0] - now
        _next[0] = max(now, _next[0]) + 60.0 / PER_MIN
    if wait > 0: time.sleep(wait)

def api(path, **p):
    p.update(api_key=KEY, file_type='json')
    u = BASE + path + '?' + urllib.parse.urlencode(p)
    for i in range(40):
        _pace(); COUNT['requests'] += 1
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'hrtd-live'}), timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                COUNT['retries'] += 1; time.sleep(min(60 * (i + 1), 600)); continue
            body = ''
            try: body = e.read().decode()[:300]
            except Exception: pass
            raise RuntimeError(f'HTTP {e.code} {re.sub(r"api_key=[^&]+", "api_key=X", body)}')
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, json.JSONDecodeError):
            COUNT['retries'] += 1; time.sleep(min(30 * (i + 1), 600)); continue
    raise RuntimeError('HTTP 429/5xx or network: gave up after 40 tries')

def obs(sid, L, E='9999-12-31'):
    out, off = [], 0
    while True:
        d = api('series/observations', series_id=sid, realtime_start=L, realtime_end=E, output_type=1, limit=100000, offset=off)
        ob = d.get('observations', [])
        out += [(o['date'], o['realtime_start'], o['realtime_end'], o['value']) for o in ob]
        off += len(ob)
        if off >= int(d.get('count', 0)) or not ob: return out

def day_before(s):
    return (dt.date.fromisoformat(s) - dt.timedelta(days=1)).isoformat()

def windowed(sid, L):
    v = [x for x in api('series/vintagedates', series_id=sid, limit=10000)['vintage_dates'] if x >= L]
    starts = v[::1900]; rows = []
    for i, s in enumerate(starts):
        e = day_before(starts[i + 1]) if i + 1 < len(starts) else '9999-12-31'
        rows += obs(sid, s, e)
    edges = set(starts[1:]); rows.sort(); out = []
    for r in rows:
        if out and r[1] in edges and out[-1][0] == r[0] and out[-1][3] == r[3] and day_before(r[1]) == out[-1][2]:
            out[-1] = (out[-1][0], out[-1][1], r[2], r[3])
        else:
            out.append(r)
    return out

def fetch(sid, L):
    """every row in force on or after day L (rows that began before L come back cut at L)"""
    try:
        return obs(sid, L), 'single'
    except RuntimeError as e:
        if 'HTTP 400' not in str(e): raise
        return windowed(sid, L), 'windows'

def updates_list():
    """FRED's list of recently updated series (about the last two weeks): {series_id: last_updated}"""
    out, off = {}, 0
    while True:
        d = api('series/updates', filter_value='all', limit=1000, offset=off)
        for s in d.get('seriess', []): out[s['id']] = s['last_updated']
        off += len(d.get('seriess', []))
        if off >= int(d.get('count', 0)) or not d.get('seriess'): break
    return out
