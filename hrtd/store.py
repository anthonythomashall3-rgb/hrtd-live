"""Where the state lives between runs: files attached to this repository's GitHub release 'state' (free, public data only).
A BASE snapshot (tar.zst, split under GitHub's 2 GB per file) plus DELTAS (only the files a run changed), applied in order.
state/HEAD.json in git names them with their SHA-256; it is changed by a git commit, so a run that dies before its commit
leaves the previous state whole. Every download is checked against its SHA-256 before use."""
import os, sys, json, hashlib, subprocess, time, glob, shutil

REPO = os.environ.get('GITHUB_REPOSITORY', 'anthonythomashall3-rgb/hrtd-live')
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADF = f'{HERE}/state/HEAD.json'
TAG = 'state'

def sh(*a, **k):
    return subprocess.run(list(a), check=True, text=True, capture_output=True, **k).stdout

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''): h.update(b)
    return h.hexdigest()

def head():
    return json.load(open(HEADF)) if os.path.exists(HEADF) else None

def restore(work, dl):
    """download (into dl) and unpack (into work) the base and every delta named in HEAD, in order"""
    H = head(); assert H, 'no state/HEAD.json'
    os.makedirs(work, exist_ok=True); os.makedirs(dl, exist_ok=True)
    for name, want in H['assets']:
        p = f'{dl}/{name}'
        if not (os.path.exists(p) and sha(p) == want):
            for i in range(5):
                try: sh('gh', 'release', 'download', TAG, '-R', REPO, '-p', name, '-D', dl, '--clobber'); break
                except subprocess.CalledProcessError:
                    if i == 4: raise
                    time.sleep(20 * (i + 1))
        got = sha(p)
        if got != want: raise RuntimeError(f'{name}: SHA-256 {got} is not {want}')
    for group in H['order']:            # a base split in parts is joined before unpacking
        files = [f'{dl}/{n}' for n in group]
        cat = subprocess.Popen(['cat'] + files, stdout=subprocess.PIPE)
        subprocess.run(['tar', '--zstd', '-xf', '-', '-C', work], stdin=cat.stdout, check=True); cat.wait()
    return H

def upload(path):
    for i in range(5):
        try: sh('gh', 'release', 'upload', TAG, path, '-R', REPO, '--clobber'); return
        except subprocess.CalledProcessError:
            if i == 4: raise
            time.sleep(20 * (i + 1))

def pack(work, rels, out):
    """tar.zst of the listed paths (relative to work)"""
    lst = out + '.list'
    with open(lst, 'w') as f: f.write('\n'.join(rels) + '\n')
    mac = ['--no-xattrs', '--no-mac-metadata', '--no-acls'] if sys.platform == 'darwin' else []   # the seed is packed on the Mac
    subprocess.run(['tar', '--zstd'] + mac + ['-cf', out, '-C', work, '-T', lst], check=True); os.remove(lst)

def save_delta(work, rels, stamp, dl):
    """upload the changed files as one delta and name it in HEAD (the caller commits HEAD)"""
    H = head(); name = f'delta-{stamp}.tar.zst'; p = f'{dl}/{name}'
    pack(work, sorted(set(rels)), p); s = sha(p); upload(p)
    H['assets'].append([name, s]); H['order'].append([name]); H['updated'] = stamp
    json.dump(H, open(HEADF, 'w'), indent=1)
    return name, os.path.getsize(p)

def save_base(work, stamp, dl, part_mb=1900):
    """a new BASE of everything in work (when the deltas pile up); older assets are kept until the next base"""
    p = f'{dl}/base-{stamp}.tar.zst'
    rels = [r for r in os.listdir(work)]
    pack(work, rels, p)
    subprocess.run(['split', '-b', f'{part_mb}m', '-d', '-a', '2', p, p + '.part'], check=True); os.remove(p)
    parts = sorted(glob.glob(p + '.part*')); assets = []
    for q in parts:
        upload(q); assets.append([os.path.basename(q), sha(q)])
    old = head()
    H = {'assets': assets, 'order': [[a[0] for a in assets]], 'updated': stamp, 'base': stamp,
         'previous': (old or {}).get('assets', [])}
    json.dump(H, open(HEADF, 'w'), indent=1)
    return [a[0] for a in assets]

def prune():
    """delete release files named by neither HEAD nor its previous base (kept one base back for a rollback)"""
    H = head(); keep = {a[0] for a in H['assets']} | {a[0] for a in H.get('previous', [])}
    names = sh('gh', 'release', 'view', TAG, '-R', REPO, '--json', 'assets', '-q', '.assets[].name').split()
    for n in names:
        if n not in keep: subprocess.run(['gh', 'release', 'delete-asset', TAG, n, '-R', REPO, '-y'], check=False)

def commit(msg):
    """commit state/HEAD.json (and anything else staged under state/ or parity/) and push; retried on a race"""
    sh('git', '-C', HERE, 'add', 'state', 'parity')
    if not sh('git', '-C', HERE, 'status', '--porcelain', 'state', 'parity').strip(): return False
    sh('git', '-C', HERE, '-c', 'user.name=hrtd runner', '-c', 'user.email=hrtd@users.noreply.github.com', 'commit', '-m', msg)
    for i in range(5):
        try: sh('git', '-C', HERE, 'push', 'origin', 'HEAD'); return True
        except subprocess.CalledProcessError:
            if i == 4: raise
            # 1116: the rebase needs a committer too (without one git stopped with status 128 whenever another push had
            # landed first, and every pass of run 43876861947 failed at this line); a rebase left half-done is dropped
            subprocess.run(['git', '-C', HERE, 'rebase', '--abort'], capture_output=True)
            sh('git', '-C', HERE, '-c', 'user.name=hrtd runner', '-c', 'user.email=hrtd@users.noreply.github.com', 'pull', '--rebase', 'origin', 'main'); time.sleep(5)
