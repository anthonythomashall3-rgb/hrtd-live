"""HRTD site data, a port of ~/Projects/hrtd/build_hrtd.py (same files, same formats, same ranking).
The series shards d/<k>.json hold every series' points; they are updated in place for changed series only. The pages built
from all series together (latest, m/, b/, s/, v/, index.json) are rebuilt from the meta rows, which is quick (no points read).
A file is written only when its bytes change, so a deploy uploads only what changed."""
import json, os, re, time, zlib
from array import array
from collections import defaultdict

NSHARD, NBUCKET, PAGE = 2048, 4096, 1000
HEADLINE = ["UNRATE", "PAYEMS", "ICSA", "GDPC1", "CPIAUCSL", "FEDFUNDS", "HOUST", "INDPRO", "T10Y2Y", "UMCSENT"]
STOP = set("of and the for in to by a an all on at from with as or per".split())
WRITTEN = {'files': 0}

def stem(t):
    if t.isdigit() or len(t) <= 3: return t
    if t.endswith("ies") and len(t) > 4: return t[:-3] + "y"
    if t.endswith("sses"): return t[:-2]
    if t.endswith("ing") and len(t) > 6: return t[:-3]
    if t.endswith("ed") and len(t) > 5: return t[:-2]
    if t.endswith("s") and not t.endswith(("ss", "us", "is")): return t[:-1]
    return t

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80] or "x"

def shard_of(sid):
    return zlib.crc32(sid.encode()) % NSHARD

def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def wjson(path, obj):
    b = dumps(obj)
    try:
        with open(path, "rb") as f:
            if f.read() == b: return False
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "wb") as f: f.write(b)
    os.replace(path + ".part", path); WRITTEN['files'] += 1
    return True

def point(date, value, release):
    """the site's point: [ISO day, repr of the float (as pandas.to_csv writes it), ISO release day or '']"""
    return [date, repr(float(value)), release or ""]

def meta_row(sid, rec):
    pts = rec["p"]
    return [sid, rec["t"], rec["q"], rec["u"], rec["sa"], rec["fn"][:2], rec["a"], rec["r"],
            pts[0][0], pts[-1][0], pts[-1][1], pts[-1][2], len(pts), pts[-36:] if sid in HEADLINE else None]

def aggregates(rows, pop, fnames, years, out):
    """build_hrtd.main() after the shards: rows = meta rows of every series (any order)."""
    rows = [list(r) for r in rows]
    rows.sort(key=lambda r: (-pop.get(r[0], 0), len(r[1]), -r[12], r[0]))
    latest = {}
    for r in rows:
        if r[13] is not None:
            latest[r[0]] = {"t": r[1], "u": r[3], "q": r[2], "a": r[6], "pts": r[13]}
        del r[13]
    wjson(f"{out}/latest.json", latest)
    for i in range(0, len(rows), PAGE):
        wjson(f"{out}/m/{i // PAGE}.json", rows[i:i + PAGE])
    facets = {"f": defaultdict(list), "a": defaultdict(list), "r": defaultdict(list), "q": defaultdict(list)}
    rel_agency = {}
    for rank, r in enumerate(rows):
        facets["f"][r[5]].append(rank); facets["a"][r[6]].append(rank)
        facets["r"][r[7]].append(rank); facets["q"][r[2]].append(rank)
        rel_agency.setdefault(r[7], r[6])
    idx = {"functions": [], "agencies": [], "releases": [], "frequencies": []}
    used = set()
    def fslug(kind, name):
        s = slug(name)
        while (kind, s) in used: s += "-2"
        used.add((kind, s)); return s
    for kind, d in facets.items():
        for name, ranks in d.items():
            s = name if kind == "f" else fslug(kind, name)
            sub = defaultdict(int)
            for rk in ranks:
                rr = rows[rk]
                sub[(rr[6], rr[7]) if kind == "f" else (rr[7] if kind == "a" else rr[5])] += 1
            npages = (len(ranks) + PAGE - 1) // PAGE
            prints = sum(rows[rk][12] for rk in ranks)
            title = fnames.get(name, name) if kind == "f" else name
            for p in range(npages):
                page = {"kind": kind, "name": title, "total": len(ranks), "pages": npages, "page": p,
                        "rows": [rows[rk] for rk in ranks[p * PAGE:(p + 1) * PAGE]]}
                if p == 0:
                    page["breakdown"] = sorted([[list(k) if isinstance(k, tuple) else k, v] for k, v in sub.items()], key=lambda x: -x[1])
                wjson(f"{out}/b/{kind}/{s}/{p}.json", page)
            entry = {"name": title, "slug": s, "n": len(ranks), "prints": prints}
            if kind == "r": entry["agency"] = rel_agency[name]
            {"f": idx["functions"], "a": idx["agencies"], "r": idx["releases"], "q": idx["frequencies"]}[kind].append(entry)
    idx["functions"].sort(key=lambda e: e["slug"])
    for k in ("agencies", "releases", "frequencies"):
        idx[k].sort(key=lambda e: -e["n"])
    post = defaultdict(lambda: array("I"))
    for rank, r in enumerate(rows):
        text = " ".join([r[0], r[1], r[6], r[7], fnames.get(r[5], ""), r[2]]).lower()
        toks = set(stem(t) for t in re.findall(r"[a-z0-9]+", text) if t not in STOP and not (len(t) == 1 and t.isalpha()))
        toks.add(re.sub(r"[^a-z0-9]", "", r[0].lower()))
        for t in sorted(toks): post[t].append(rank)   # sorted: the Mac's set order changes every run (same content, 1115 test)
    buckets = defaultdict(dict); vocab = defaultdict(list)
    for t, arr in post.items():
        buckets[zlib.crc32(t.encode()) % NBUCKET][t] = arr.tolist()
        vocab[t[:2]].append([t, len(arr)])
    for b in range(NBUCKET):
        wjson(f"{out}/s/{b}.json", buckets.get(b, {}))
    for p, lst in vocab.items():
        lst.sort(key=lambda x: -x[1])
        wjson(f"{out}/v/{p}.json", lst)
    total_prints = sum(r[12] for r in rows)
    last_rel = max((r[11] for r in rows if r[11]), default="")
    idx["totals"] = {"series": len(rows), "prints": total_prints, "agencies": len(facets["a"]), "releases": len(facets["r"]),
                     "functions": len(facets["f"]), "earliest": min(r[8] for r in rows), "latest_release": last_rel,
                     "built": time.strftime("%Y-%m-%d %H:%M %Z"), "meta_pages": (len(rows) + PAGE - 1) // PAGE,
                     "nshard": NSHARD, "nbucket": NBUCKET}
    idx["years"] = years
    wjson(f"{out}/index.json", idx)
    return idx["totals"]
