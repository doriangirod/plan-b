// Plan B - Weather Risk — logique partagée par index.html (EN) et fr.html (FR).
// La langue est lue dans <html lang="..."> de chaque page.
// Le calcul (section MODÈLE) est la traduction exacte de model.py :
// si tu modifies les maths dans model.py, reporte la modification ici.

// ---------- Réglages ----------
const WINDOW_DAYS = 7;      // demi-largeur de la fenêtre climatologique
const N_YEARS = 30;         // années d'historique
const FORECAST_DAYS = 16;   // horizon max de la prévision Open-Meteo
const Z = 1.96;             // quantile pour l'intervalle à 95 %

const Y1 = new Date().getFullYear() - 1;   // dernière année complète
const Y0 = Y1 - N_YEARS + 1;

// ---------- Textes ----------
const LANG = document.documentElement.lang === 'en' ? 'en' : 'fr';
const LOCALE = LANG === 'en' ? 'en-CH' : 'fr-CH';
const T = {
  fr: {
    netErr: w => `Impossible de joindre le service météo (${w}). Vérifiez la connexion.`,
    httpErr: (w, c) => `Le service météo a refusé la requête (${w}, code ${c}).`,
    wGeo: 'recherche du lieu', wHist: 'historique', wFc: 'prévision',
    notFound: n => `Lieu introuvable : « ${n} ». Essayez le nom d'une commune, sans le pays.`,
    needPlace: 'Indiquez un lieu et une date.',
    badNums: 'Vérifiez les montants : recette et perte doivent être positives, la perte au plus 100 %.',
    past: 'La date est passée. Choisissez une date à venir.',
    locating: 'Recherche du lieu…',
    reading: (y, n) => `Lecture de ${y} ans de données pour ${n}…`,
    noData: 'Pas assez de données historiques pour ce lieu.',
    summary: (where, d, h, k, n) => `${where} · ${d} (dans ${h} j) · ${k} jours de pluie sur ${n} dans l'historique`,
    fcNote: p => ` · prévision : ${p} %`,
    lean: up => up ? 'penche vers la protection' : 'penche vers l\'absence de protection',
    protect: (p, el, c) => ['Protéger', 'La protection est rentable',
      `Avec ${p} de risque de pluie, la perte attendue (${el}) dépasse le coût de la protection (${c}).`],
    skip: (p, el, c) => ['Ne pas protéger', 'La protection coûte plus qu\'elle ne rapporte',
      `Avec ${p} de risque de pluie, la perte attendue (${el}) reste sous le coût de la protection (${c}).`],
    close: (lo, hi, ps, lean) => ['Décision serrée', 'Le seuil est dans la marge d\'incertitude',
      `La probabilité se situe entre ${lo} et ${hi}, et le seuil de rentabilité est de ${ps}. Le calcul ${lean}, mais l'écart n'est pas significatif.`],
    range: (lo, hi) => `${lo} à ${hi}`,
    fcWeight: w => ` · prévision ${w} %`, climOnly: ' · climatologie',
    ofRev: (l, r) => `${l} % de ${r}`,
    protCost: c => `protection : ${c}`,
    never: 'jamais rentable', above: 'protéger au-delà',
    day0: 'J · '
  },
  en: {
    netErr: w => `Could not reach the weather service (${w}). Check your connection.`,
    httpErr: (w, c) => `The weather service rejected the request (${w}, code ${c}).`,
    wGeo: 'location search', wHist: 'history', wFc: 'forecast',
    notFound: n => `Location not found: "${n}". Try a town name without the country.`,
    needPlace: 'Enter a location and a date.',
    badNums: 'Check the amounts: revenue and loss must be positive, and the loss at most 100%.',
    past: 'That date has passed. Pick a future date.',
    locating: 'Finding the location…',
    reading: (y, n) => `Reading ${y} years of data for ${n}…`,
    noData: 'Not enough historical data for this location.',
    summary: (where, d, h, k, n) => `${where} · ${d} (in ${h} days) · ${k} rainy days out of ${n} in the record`,
    fcNote: p => ` · forecast: ${p}%`,
    lean: up => up ? 'leans towards protecting' : 'leans towards not protecting',
    protect: (p, el, c) => ['Protect', 'Protection pays off',
      `With a ${p} chance of rain, the expected loss (${el}) exceeds the cost of protection (${c}).`],
    skip: (p, el, c) => ['Don\'t protect', 'Protection costs more than it saves',
      `With a ${p} chance of rain, the expected loss (${el}) stays below the cost of protection (${c}).`],
    close: (lo, hi, ps, lean) => ['Close call', 'The threshold is within the uncertainty',
      `The probability lies between ${lo} and ${hi}, and the break-even threshold is ${ps}. The estimate ${lean}, but the gap is not significant.`],
    range: (lo, hi) => `${lo} to ${hi}`,
    fcWeight: w => ` · forecast ${w}%`, climOnly: ' · climatology',
    ofRev: (l, r) => `${l}% of ${r}`,
    protCost: c => `protection: ${c}`,
    never: 'never pays off', above: 'protect above this',
    day0: 'D · '
  }
}[LANG];

// ---------- Utilitaires ----------
const $ = id => document.getElementById(id);
const iso = d => d.toISOString().slice(0, 10);
const addDays = (d, k) => { const e = new Date(d); e.setUTCDate(e.getUTCDate() + k); return e; };
const parseISO = s => { const [y, m, d] = s.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)); };
const todayUTC = () => { const t = new Date(); return new Date(Date.UTC(t.getFullYear(), t.getMonth(), t.getDate())); };
const chf = x => new Intl.NumberFormat(LOCALE, { style: 'currency', currency: 'CHF', maximumFractionDigits: 0 }).format(x);
const pct = x => (x < 0.1 ? (100 * x).toFixed(1) : (100 * x).toFixed(0)) + (LANG === 'fr' ? ' %' : '%');
const dayLabel = d => d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', timeZone: 'UTC' });

// ---------- Données (Open-Meteo, sans clé) ----------
const histCache = new Map();

async function getJSON(url, what) {
  let r;
  try { r = await fetch(url); } catch (e) { throw new Error(T.netErr(what)); }
  if (!r.ok) throw new Error(T.httpErr(what, r.status));
  return r.json();
}

async function geocode(name) {
  const u = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(name)}&count=1&language=${LANG}&format=json`;
  const j = await getJSON(u, T.wGeo);
  if (!j.results || !j.results.length) throw new Error(T.notFound(name));
  return j.results[0];
}

async function fetchHistory(lat, lon) {
  const key = `${lat.toFixed(3)},${lon.toFixed(3)}`;
  if (histCache.has(key)) return histCache.get(key);
  const u = `https://archive-api.open-meteo.com/v1/archive?latitude=${lat}&longitude=${lon}` +
            `&start_date=${Y0}-01-01&end_date=${Y1}-12-31&daily=precipitation_sum&timezone=Europe%2FZurich`;
  const j = await getJSON(u, T.wHist);
  const m = new Map();
  j.daily.time.forEach((t, i) => { const v = j.daily.precipitation_sum[i]; if (v != null) m.set(t, v); });
  histCache.set(key, m);
  return m;
}

async function fetchForecast(lat, lon, dateStr) {
  const u = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
            `&daily=precipitation_probability_max,precipitation_sum&timezone=Europe%2FZurich&forecast_days=${FORECAST_DAYS}`;
  const j = await getJSON(u, T.wFc);
  const i = j.daily.time.indexOf(dateStr);
  if (i < 0) return null;
  const pp = j.daily.precipitation_probability_max[i];
  return pp == null ? null : { pf: pp / 100, mm: j.daily.precipitation_sum[i] };
}

// ---------- Statistiques ----------
// Compte les jours de pluie (>= seuil) dans la fenêtre ±W autour du même jour calendaire, chaque année.
function climatology(hist, month, day, thr, W) {
  let k = 0, n = 0;
  for (let y = Y0; y <= Y1; y++) {
    const c = new Date(Date.UTC(y, month, day));
    for (let o = -W; o <= W; o++) {
      const v = hist.get(iso(addDays(c, o)));
      if (v === undefined) continue;
      n++; if (v >= thr) k++;
    }
  }
  return { k, n };
}

// Fréquence de pluie jour par jour (sur 30 ans) pour le graphique.
function dailyProfile(hist, month, day, thr, span) {
  const out = [];
  for (let o = -span; o <= span; o++) {
    let k = 0, n = 0;
    for (let y = Y0; y <= Y1; y++) {
      const v = hist.get(iso(addDays(new Date(Date.UTC(y, month, day)), o)));
      if (v === undefined) continue;
      n++; if (v >= thr) k++;
    }
    out.push({ o, f: n ? k / n : 0 });
  }
  return out;
}

function wilson(k, n, z) {
  const p = k / n, z2 = z * z, den = 1 + z2 / n;
  const centre = (p + z2 / (2 * n)) / den;
  const half = (z / den) * Math.sqrt(p * (1 - p) / n + z2 / (4 * n * n));
  return [Math.max(0, centre - half), Math.min(1, centre + half)];
}

// ================= MODÈLE (ta partie : c'est ici que tu modifies les maths) =================
function computeRisk({ k, n, pf, h, R, lambda, C }) {
  const pc = k / n;                                   // climatologie
  const [lo, hi] = wilson(k, n, Z);
  const w = pf == null ? 0 : Math.max(0, 1 - h / FORECAST_DAYS);   // poids de la prévision
  const p = w * pf + (1 - w) * pc;
  const pLo = w * (pf ?? 0) + (1 - w) * lo;
  const pHi = w * (pf ?? 0) + (1 - w) * hi;

  const loss = lambda * R;                            // perte si pluie
  const EL = p * loss;                                // perte attendue
  const pStar = loss > 0 ? C / loss : Infinity;       // seuil de décision

  let decision;
  if (pLo > pStar) decision = 'protect';
  else if (pHi < pStar) decision = 'skip';
  else decision = 'close';

  return { pc, lo, hi, w, p, pLo, pHi, loss, EL, pStar, decision };
}
// ===========================================================================================

// ---------- Affichage ----------
function renderVerdict(r, ctx) {
  $('verdict').className = 'verdict ' + r.decision;
  const [tag, title, text] = r.decision === 'close'
    ? T.close(pct(r.pLo), pct(r.pHi), pct(r.pStar), T.lean(r.p > r.pStar))
    : T[r.decision](pct(r.p), chf(r.EL), chf(ctx.C));
  $('vtag').textContent = tag; $('vtitle').textContent = title; $('vtext').textContent = text;

  $('fp').textContent = pct(r.p);
  $('fps').textContent = T.range(pct(r.pLo), pct(r.pHi)) + (r.w > 0 ? T.fcWeight(Math.round(100 * r.w)) : T.climOnly);
  $('fl').textContent = chf(r.loss);
  $('fls').textContent = T.ofRev(Math.round(ctx.lambda * 100), chf(ctx.R));
  $('fe').textContent = chf(r.EL);
  $('fes').textContent = T.protCost(chf(ctx.C));
  $('fs').textContent = isFinite(r.pStar) ? pct(Math.min(r.pStar, 1)) : '—';
  $('fss').textContent = r.pStar > 1 ? T.never : T.above;
}

function renderChart(profile, r, eventDate) {
  const svg = $('chart');
  const W = 760, H = 140, m = { l: 44, r: 16, t: 10, b: 26 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const maxF = Math.max(...profile.map(d => d.f), r.p, isFinite(r.pStar) ? Math.min(r.pStar, 1) : 0);
  const yMax = Math.min(1, Math.ceil((maxF + 0.05) * 10) / 10);
  const span = (profile.length - 1) / 2;
  const slot = iw / profile.length;
  const x = o => m.l + (o + span + 0.5) * slot;
  const y = v => m.t + ih - (v / yMax) * ih;
  const bw = slot * 0.72;
  let s = `<rect class="win" x="${x(-WINDOW_DAYS) - slot / 2}" y="${m.t}" width="${(2 * WINDOW_DAYS + 1) * slot}" height="${ih}"/>`;
  const step = yMax > 0.5 ? 0.2 : 0.1;
  for (let t = 0; t <= yMax + 1e-9; t += step) {
    s += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/>`;
    s += `<text x="${m.l - 8}" y="${y(t) + 4}" text-anchor="end">${Math.round(t * 100)}%</text>`;
  }
  profile.forEach(d => {
    const out = Math.abs(d.o) > WINDOW_DAYS ? ' out' : '';
    s += `<rect class="bar${out}" x="${x(d.o) - bw / 2}" y="${y(d.f)}" width="${bw}" height="${Math.max(0, m.t + ih - y(d.f))}"><title>${dayLabel(addDays(eventDate, d.o))}: ${pct(d.f)}</title></rect>`;
  });
  [-30, -15, 0, 15, 30].filter(o => Math.abs(o) <= span).forEach(o => {
    s += `<text x="${x(o)}" y="${H - 6}" text-anchor="middle">${o === 0 ? T.day0 : ''}${dayLabel(addDays(eventDate, o))}</text>`;
  });
  s += `<line class="pmean" x1="${m.l}" x2="${W - m.r}" y1="${y(r.p)}" y2="${y(r.p)}"/>`;
  s += `<text class="pmean-l" x="${W - m.r - 4}" y="${y(r.p) - 5}" text-anchor="end">p = ${pct(r.p)}</text>`;
  if (isFinite(r.pStar) && r.pStar <= yMax) {
    s += `<line class="pstar" x1="${m.l}" x2="${W - m.r}" y1="${y(r.pStar)}" y2="${y(r.pStar)}"/>`;
    s += `<text class="pstar-l" x="${m.l + 6}" y="${y(r.pStar) - 5}">p* = ${pct(r.pStar)}</text>`;
  }
  svg.innerHTML = s;
}

// ---------- Orchestration ----------
async function run(ev) {
  if (ev) ev.preventDefault();
  const status = $('status'), btn = $('go'), figs = document.querySelector('.figs');
  const ctx = {
    place: $('place').value.trim(), date: $('date').value,
    R: +$('rev').value, lambda: +$('lam').value / 100, C: +$('cost').value, thr: +$('thr').value
  };
  const fail = msg => { status.className = 'status err'; status.textContent = msg; };
  status.className = 'status';
  if (!ctx.place || !ctx.date) return fail(T.needPlace);
  if (!(ctx.R > 0) || !(ctx.lambda > 0) || ctx.lambda > 1 || !(ctx.C >= 0) || !(ctx.thr > 0)) return fail(T.badNums);
  const eventDate = parseISO(ctx.date);
  const h = Math.round((eventDate - todayUTC()) / 86400000);
  if (h < 0) return fail(T.past);

  btn.disabled = true; figs.classList.add('dim');
  try {
    status.textContent = T.locating;
    const loc = await geocode(ctx.place);
    status.textContent = T.reading(N_YEARS, loc.name);
    const [hist, fc] = await Promise.all([
      fetchHistory(loc.latitude, loc.longitude),
      h < FORECAST_DAYS ? fetchForecast(loc.latitude, loc.longitude, ctx.date).catch(() => null) : Promise.resolve(null)
    ]);
    const M = eventDate.getUTCMonth(), D = eventDate.getUTCDate();
    const { k, n } = climatology(hist, M, D, ctx.thr, WINDOW_DAYS);
    if (n < 30) throw new Error(T.noData);
    const r = computeRisk({ k, n, pf: fc ? fc.pf : null, h, R: ctx.R, lambda: ctx.lambda, C: ctx.C });
    renderVerdict(r, ctx);
    renderChart(dailyProfile(hist, M, D, ctx.thr, 30), r, eventDate);
    const where = [loc.name, loc.admin1, loc.country].filter(Boolean).join(', ');
    status.textContent = T.summary(where, dayLabel(eventDate), h, k, n) + (fc ? T.fcNote(Math.round(fc.pf * 100)) : '');
  } catch (e) {
    fail(e.message);
  } finally {
    btn.disabled = false; figs.classList.remove('dim');
  }
}

$('f').addEventListener('submit', run);
$('date').value = iso(addDays(todayUTC(), 10));   // exemple : événement dans 10 jours
run();
