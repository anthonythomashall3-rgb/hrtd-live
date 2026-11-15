/* HRTD shared code: chrome, data access, search, formatting */
const H = {};
H.cache = new Map();
H.get = (url) => {
  if (!H.cache.has(url)) H.cache.set(url, fetch(url).then(r => { if (!r.ok) throw new Error(r.status + ' ' + url); return r.json(); }));
  return H.cache.get(url);
};
H.idx = () => H.get('/data/index.json');
H.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
H.qs = (k) => new URLSearchParams(location.search).get(k);
H.int = (n) => Number(n).toLocaleString('en-US');

const CRC = (() => { const t = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
H.crc32 = (s) => { let c = 0xFFFFFFFF; for (const x of new TextEncoder().encode(s)) c = CRC[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };

/* formatting: values are shown exactly as published; only thousands separators are added */
H.val = (v) => {
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(v));
  if (!m) return H.esc(v);
  const ip = m[2].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const fr = m[3] && !/^0+$/.test(m[3]) ? '.' + m[3] : '';
  return m[1] + ip + fr;
};
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
H.date = (d) => { if (!d) return ''; const [y, m, dd] = d.split('-'); return m ? `${MON[+m - 1]} ${+dd}, ${y}` : d; };
H.period = (d, q) => {
  if (!d) return '';
  const [y, m] = d.split('-'); q = q || '';
  if (q.startsWith('Monthly')) return `${MON[+m - 1]} ${y}`;
  if (q.startsWith('Quarterly')) return `Q${Math.floor((+m - 1) / 3) + 1} ${y}`;
  if (q.startsWith('Semiannual')) return `H${+m <= 6 ? 1 : 2} ${y}`;
  if (q.startsWith('Annual')) return y;
  if (q.startsWith('Weekly')) return 'w/e ' + H.date(d);
  return H.date(d);
};
H.spark = (vals, w = 120, h = 32) => {
  const v = vals.map(Number).filter(x => !isNaN(x)); if (v.length < 2) return '';
  const lo = Math.min(...v), hi = Math.max(...v), r = (hi - lo) || 1;
  return v.map((x, i) => `${i ? 'L' : 'M'}${(2 + i * (w - 4) / (v.length - 1)).toFixed(1)},${(2 + (h - 4) * (1 - (x - lo) / r)).toFixed(1)}`).join(' ');
};
H.seriesUrl = (id) => '/series/?id=' + encodeURIComponent(id);

/* best-known sources, grouped */
H.GROUPS = [
  { key: 'bls', label: 'Bureau of Labor Statistics (BLS)', m: a => a === 'U.S. Bureau of Labor Statistics' },
  { key: 'bea', label: 'Bureau of Economic Analysis (BEA)', m: a => a === 'U.S. Bureau of Economic Analysis' },
  { key: 'census', label: 'U.S. Census Bureau', m: a => a === 'U.S. Census Bureau' },
  { key: 'frb', label: 'Federal Reserve Board', m: a => a === 'Board of Governors of the Federal Reserve System (US)' },
  { key: 'fed-banks', label: 'Regional Federal Reserve Banks', m: a => a.startsWith('Federal Reserve Bank of') },
  { key: 'treasury', label: 'U.S. Department of the Treasury', m: a => a.startsWith('U.S. Department of the Treasury') },
  { key: 'labor', label: 'Department of Labor / ETA', m: a => a === 'U.S. Employment and Training Administration' || a === 'U.S. Department of Labor' },
  { key: 'eia', label: 'Energy Information Administration', m: a => a === 'U.S. Energy Information Administration' },
  { key: 'fhfa', label: 'Federal Housing Finance Agency', m: a => a === 'U.S. Federal Housing Finance Agency' },
  { key: 'ffiec', label: 'FFIEC', m: a => a.startsWith('Federal Financial Institutions Examination Council') },
  { key: 'fdic', label: 'FDIC', m: a => a === 'Federal Deposit Insurance Corporation' },
];
H.groupInfo = (idx, g) => {
  const mem = idx.agencies.filter(a => g.m(a.name));
  const n = mem.reduce((s, a) => s + a.n, 0);
  const url = mem.length === 1 ? `/browse/?k=a&s=${encodeURIComponent(mem[0].slug)}` : `/browse/?g=${g.key}`;
  return { mem, n, url };
};
H.find = (list, name) => list.find(e => e.name === name);
H.browseUrl = (k, s, p) => `/browse/?k=${k}&s=${encodeURIComponent(s)}${p ? '&p=' + p : ''}`;

/* site chrome */
H.chrome = () => {
  const hd = document.getElementById('hdr'), ft = document.getElementById('ftr');
  if (hd) hd.innerHTML = `<div class="top">A research database of the Bristow-Hall Program · Real-time U.S. economic data</div>
<header class="site"><a class="brand" href="/"><b>HRTD</b><span>Hall Realtime Database</span></a>
<nav aria-label="Main"><a href="/browse/">Browse Data</a><a href="/calendar/">Release Calendar</a><a href="/methodology/">Methodology</a><a href="/downloads/">Downloads</a><a href="/about/">About</a></nav>
${hd.dataset.nosearch ? '' : `<form class="hsearch" action="/search/" method="get" role="search"><label for="hq" class="sr">Search series</label><input id="hq" name="q" placeholder="Search series" value="${H.esc(H.qs('q') || '')}"><button>Search</button></form>`}</header>`;
  if (ft) {
    ft.innerHTML = `<footer class="site">HRTD · Hall Realtime Database · Bristow-Hall Program, University of Southern California<span id="built"></span></footer>`;
    H.idx().then(i => { document.getElementById('built').textContent = ` · Data built ${i.totals.built}`; }).catch(() => {});
  }
};

/* search */
const STOP = new Set('of and the for in to by a an all on at from with as or per'.split(' '));
H.stem = (t) => {
  if (/^\d+$/.test(t) || t.length <= 3) return t;
  if (t.endsWith('ies') && t.length > 4) return t.slice(0, -3) + 'y';
  if (t.endsWith('sses')) return t.slice(0, -2);
  if (t.endsWith('ing') && t.length > 6) return t.slice(0, -3);
  if (t.endsWith('ed') && t.length > 5) return t.slice(0, -2);
  if (t.endsWith('s') && !/(ss|us|is)$/.test(t)) return t.slice(0, -1);
  return t;
};
H.tokens = (q) => (q.toLowerCase().match(/[a-z0-9]+/g) || []).filter(t => !STOP.has(t) && !(t.length === 1 && /[a-z]/.test(t))).map(H.stem);
H.bucket = async (t) => { const i = await H.idx(); const b = await H.get(`/data/s/${H.crc32(t) % i.totals.nbucket}.json`); return b[t] || null; };
H.postings = async (t, last) => {
  const exact = await H.bucket(t);
  if (!last || t.length < 3) return exact || [];
  let voc = [];
  try { voc = await H.get(`/data/v/${t.slice(0, 2)}.json`); } catch (e) { }
  const cands = voc.filter(x => x[0].startsWith(t)).slice(0, 12).map(x => x[0]);
  if (exact && !cands.includes(t)) cands.unshift(t);
  if (cands.length <= 1) return exact || [];
  const lists = await Promise.all(cands.map(H.bucket));
  const s = new Set(); lists.forEach(l => l && l.forEach(x => s.add(x)));
  return [...s].sort((a, b) => a - b);
};
H.metaRows = async (ranks) => {
  const i = await H.idx(), ms = i.totals.meta_size || 1000;
  const pages = [...new Set(ranks.map(r => Math.floor(r / ms)))];
  const got = await Promise.all(pages.map(p => H.get(`/data/m/${p}.json`)));
  const map = new Map(); pages.forEach((p, j) => map.set(p, got[j]));
  return ranks.map(r => map.get(Math.floor(r / ms))[r % ms]);
};
H.search = async (q) => {
  const ts = H.tokens(q);
  if (!ts.length) return [];
  const lists = await Promise.all(ts.map((t, i) => H.postings(t, i === ts.length - 1)));
  lists.sort((a, b) => a.length - b.length);
  let res = lists[0];
  for (let i = 1; i < lists.length && res.length; i++) { const s = new Set(lists[i]); res = res.filter(x => s.has(x)); }
  const idt = q.toLowerCase().replace(/[^a-z0-9]/g, '');
  if (idt) {
    const ex = await H.bucket(idt);
    if (ex && ex.length <= 50) {
      const rows = await H.metaRows(ex);
      const hit = ex.filter((r, j) => rows[j][0].toLowerCase().replace(/[^a-z0-9]/g, '') === idt);
      if (hit.length) { const hs = new Set(hit); res = hit.concat(res.filter(x => !hs.has(x))); }
    }
  }
  return res;
};

/* row = [id,title,freq,units,sa,fno,agency,release,first,last,lastValue,lastRelease,n] */
H.rowHtml = (r) => `<div class="hit"><a class="ttl" href="${H.seriesUrl(r[0])}">${H.esc(r[1])}</a>
<div class="m">${H.esc(r[0])} · ${H.esc(r[2])} · ${H.esc(r[3])}${r[4] ? ' · ' + H.esc(r[4]) : ''}</div>
<div class="m">${H.period(r[8], r[2])} – ${H.period(r[9], r[2])} · ${H.int(r[12])} first prints · latest ${H.val(r[10])}${r[11] ? ' (released ' + H.date(r[11]) + ')' : ''} · ${H.esc(r[6])}</div></div>`;

document.addEventListener('DOMContentLoaded', H.chrome);
