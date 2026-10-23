"""
Backtest de la climatologie de Plan B (sans toucher au site).

Idée : on se place dans le passé. Pour chaque jour des années test (2016-2025), on calcule ce que
Plan B aurait annoncé avec SEULEMENT les années précédentes (méthode « l'année comme unité » de
python/model.py), puis on compare avec ce qui s'est réellement passé ce jour-là (o = 1 si pluie >= t).

Ce que le script mesure :
  1. Biais        : probabilité annoncée en moyenne vs fréquence observée.
  2. Fiabilité    : quand Plan B annonce ~20 %, pleut-il ~20 % du temps ?
  3. Score de Brier BS = moyenne de (p - o)², comparé à une référence sans saison (BSS = 1 - BS/BS_ref).
  4. Décisions    : coût moyen en suivant Plan B vs « toujours protéger », « jamais protéger » et
                    « information parfaite », pour plusieurs seuils de rentabilité p* = C / (lambda R).
  On compare aussi 30, 15 et 10 années d'historique (question de la stationnarité).

Seule la climatologie est testée (= ce que le site affiche quand l'événement est à plus de 16 jours) :
les prévisions archivées d'Open-Meteo ne donnent pas la probabilité de pluie par horizon.

Lancer depuis le dossier Plan B :   .venv/bin/python analyse/backtest.py
  - premier lancement : ~10 min de téléchargement (gardé dans analyse/cache/, pas retéléchargé ensuite)
  - test sans internet avec des données inventées : BACKTEST_SIMULE=1 .venv/bin/python analyse/backtest.py
Résultats : affichés + analyse/backtest_scores.csv, backtest_fiabilite.csv, backtest_decisions.csv
"""
import csv, json, math, os, random, sys, time
from datetime import date, timedelta

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ICI, "..", "python"))
import model   # même calcul que le site (year_interval, climatology)

VILLES = {            # nom: (lat, lon)
    "Zurich":  (47.37, 8.55),
    "Genève":  (46.20, 6.15),
    "Lugano":  (46.00, 8.95),
    "Séville": (37.39, -5.98),   # climat sec en été : petits p
}
ANNEES_TEST = range(2016, 2026)       # années où l'on « prédit »
LONGUEURS = [30, 15, 10]              # nombre d'années d'historique comparées
SEUILS = [2.0, 10.0]                  # mm
P_STARS = [0.05, 0.10, 0.20, 0.30, 0.50]   # seuils de rentabilité p* = C / (lambda R) testés
BINS = [0, .05, .10, .15, .20, .30, .40, .50, .70, 1.0001]
W = model.WINDOW_DAYS
Y_DEBUT = min(ANNEES_TEST) - max(LONGUEURS)
Y_FIN = max(ANNEES_TEST)
SIMULE = os.environ.get("BACKTEST_SIMULE") == "1"
CACHE = os.path.join(ICI, "cache")
os.makedirs(CACHE, exist_ok=True)


# ---------------------------------------------------------------- données
def telecharger(url):
    """GET avec plusieurs essais (lenteur, coupure, quota)."""
    import requests
    for essai in range(8):
        try:
            r = requests.get(url, timeout=(10, 60))
            if r.status_code == 429:
                print("   quota atteint, pause 60 s ...", flush=True); time.sleep(60); continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            attente = min(5 * 2 ** essai, 120)
            print(f"   problème réseau ({type(e).__name__}), nouvel essai dans {attente} s ...", flush=True)
            time.sleep(attente)
    raise RuntimeError("Open-Meteo ne répond pas. Relance plus tard : le script reprend où il s'est arrêté.")


def annee_simulee(lat, y):
    """Données inventées (test sans internet) : chaîne de Markov avec saison et légère tendance."""
    rnd = random.Random(f"{lat}-{y}")
    out, pluie = {}, False
    d = date(y, 1, 1)
    while d.year == y:
        base = 0.30 + 0.12 * math.cos(2 * math.pi * (d.timetuple().tm_yday - 30) / 365) - 0.002 * (y - 2000)
        p = min(0.95, base + (0.25 if pluie else 0))
        pluie = rnd.random() < p
        out[d.isoformat()] = rnd.expovariate(1 / 6) if pluie else 0.0
        d += timedelta(days=1)
    return out


def historique(lat, lon):
    """Pluie journalière {date: mm} de Y_DEBUT à Y_FIN. Une requête par année (~26 appels Open-Meteo),
    espacées pour rester sous 600 appels / minute. Chaque année est gardée dans analyse/cache/."""
    hist = {}
    for y in range(Y_DEBUT, Y_FIN + 1):
        if SIMULE:
            jour = annee_simulee(lat, y)
        else:
            f = os.path.join(CACHE, f"annee_{lat}_{lon}_{y}.json")
            if os.path.exists(f):
                with open(f, encoding="utf-8") as fh:
                    jour = json.load(fh)
            else:
                url = ("https://archive-api.open-meteo.com/v1/archive"
                       f"?latitude={lat}&longitude={lon}&start_date={y}-01-01&end_date={y}-12-31"
                       "&daily=precipitation_sum&timezone=Europe%2FZurich")
                j = telecharger(url)
                jour = {t: v for t, v in zip(j["daily"]["time"], j["daily"]["precipitation_sum"]) if v is not None}
                with open(f, "w", encoding="utf-8") as fh:
                    json.dump(jour, fh)
                time.sleep(3)
        for t, v in jour.items():
            hist[date.fromisoformat(t)] = v
    return hist


# ---------------------------------------------------------------- calculs
def predictions(hist, thr):
    """Pour chaque jour des années test : (p_hat, bas, haut) pour chaque longueur L, et o observé.
    La référence « sans saison » = fréquence sur tous les jours des 30 années précédentes."""
    lignes = []
    for Ytest in ANNEES_TEST:
        anciens = [v for d, v in hist.items() if Ytest - 30 <= d.year < Ytest]
        ref = sum(v >= thr for v in anciens) / len(anciens)
        d = date(Ytest, 1, 1)
        while d.year == Ytest:
            if d in hist and not (d.month == 2 and d.day == 29):
                L_res = {}
                for L in LONGUEURS:
                    yrs = model.climatology(hist, d.month, d.day, thr, range(Ytest - L, Ytest))
                    p, lo, hi, _, _ = model.year_interval(yrs)
                    L_res[L] = (p, lo, hi)
                lignes.append(dict(jour=d, o=int(hist[d] >= thr), ref=ref, L=L_res))
            d += timedelta(days=1)
    return lignes


def decision(p, lo, hi, ps):
    """Verdict du site (éq. 12). « Serré » -> on suit l'estimation ponctuelle (ce que le texte suggère)."""
    if lo > ps:
        return 1, False
    if hi < ps:
        return 0, False
    return int(p > ps), True


lignes_scores, lignes_fiab, lignes_dec = [], [], []
for ville, (lat, lon) in VILLES.items():
    print(f"Données {ville} ({Y_DEBUT}-{Y_FIN}) ...", flush=True)
    hist = historique(lat, lon)
    for thr in SEUILS:
        preds = predictions(hist, thr)
        o = [r["o"] for r in preds]
        N, freq = len(o), sum(o) / len(o)
        bs_ref = sum((r["ref"] - r["o"]) ** 2 for r in preds) / N
        for L in LONGUEURS:
            p = [r["L"][L][0] for r in preds]
            bs = sum((pi - oi) ** 2 for pi, oi in zip(p, o)) / N
            lignes_scores.append(dict(
                ville=ville, seuil_mm=thr, annees=L, n_jours=N,
                p_annonce_moyen=round(sum(p) / N, 4), freq_observee=round(freq, 4),
                biais=round(sum(p) / N - freq, 4), brier=round(bs, 4), brier_ref_sans_saison=round(bs_ref, 4),
                bss=round(1 - bs / bs_ref, 4),
                largeur_moy_intervalle=round(sum(r["L"][L][2] - r["L"][L][1] for r in preds) / N, 4)))
            for a, b in zip(BINS[:-1], BINS[1:]):
                idx = [i for i, pi in enumerate(p) if a <= pi < b]
                if idx:
                    lignes_fiab.append(dict(
                        ville=ville, seuil_mm=thr, annees=L, classe=f"{a:.2f}-{min(b, 1):.2f}", n_jours=len(idx),
                        p_annonce_moyen=round(sum(p[i] for i in idx) / len(idx), 4),
                        freq_observee=round(sum(o[i] for i in idx) / len(idx), 4)))
            for ps in P_STARS:
                # coûts en unités de la perte lambda*R : protéger coûte p*, pluie sans protection coûte 1
                cout_modele = serres = 0
                for r in preds:
                    prot, serre = decision(*r["L"][L], ps)
                    cout_modele += ps if prot else r["o"]
                    serres += serre
                c_mod, c_tjrs, c_jamais, c_parfait = cout_modele / N, ps, freq, ps * freq
                meilleur_naif = min(c_tjrs, c_jamais)
                valeur = (meilleur_naif - c_mod) / (meilleur_naif - c_parfait) if meilleur_naif > c_parfait else float("nan")
                lignes_dec.append(dict(
                    ville=ville, seuil_mm=thr, annees=L, p_star=ps,
                    cout_planb=round(c_mod, 4), cout_toujours=round(c_tjrs, 4), cout_jamais=round(c_jamais, 4),
                    cout_info_parfaite=round(c_parfait, 4), valeur=round(valeur, 3), part_serre=round(serres / N, 3)))


def ecrire(nom, lignes):
    with open(os.path.join(ICI, nom), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(lignes[0]))
        wr.writeheader(); wr.writerows(lignes)


suffixe = "_SIMULE" if SIMULE else ""
ecrire(f"backtest_scores{suffixe}.csv", lignes_scores)
ecrire(f"backtest_fiabilite{suffixe}.csv", lignes_fiab)
ecrire(f"backtest_decisions{suffixe}.csv", lignes_dec)

if SIMULE:
    print("\n*** DONNÉES INVENTÉES (test du script) : ces chiffres ne veulent rien dire. ***")
print("\n1. Biais et score de Brier (BSS > 0 : mieux que la référence sans saison ; biais > 0 : Plan B surestime)")
print(f"{'ville':8} {'t':>4} {'ans':>4} | {'annoncé':>7} {'observé':>7} {'biais':>7} | {'Brier':>6} {'BSS':>6} | {'larg. IC':>8}")
for s in lignes_scores:
    print(f"{s['ville']:8} {s['seuil_mm']:>4.0f} {s['annees']:>4} | {s['p_annonce_moyen']:>7.3f} {s['freq_observee']:>7.3f} "
          f"{s['biais']:>+7.3f} | {s['brier']:>6.3f} {s['bss']:>+6.3f} | {s['largeur_moy_intervalle']:>8.3f}")

print("\n2. Fiabilité (30 ans, toutes villes et seuils réunis) : annoncé vs observé par classe")
tot = {}
for f in lignes_fiab:
    if f["annees"] == 30:
        t = tot.setdefault(f["classe"], [0, 0.0, 0.0])
        t[0] += f["n_jours"]; t[1] += f["p_annonce_moyen"] * f["n_jours"]; t[2] += f["freq_observee"] * f["n_jours"]
print(f"{'classe':>10} {'jours':>7} {'annoncé':>8} {'observé':>8}")
for c in sorted(tot):
    n, a, b = tot[c]
    print(f"{c:>10} {n:>7} {a / n:>8.3f} {b / n:>8.3f}")

print("\n3. Valeur des décisions (30 ans), moyenne sur villes et seuils.")
print("   valeur = 1 : aussi bien que l'information parfaite ; 0 : pas mieux que la meilleure règle fixe ; < 0 : pire")
print(f"{'p*':>5} {'valeur':>7} {'part serré':>11}")
for ps in P_STARS:
    v = [d["valeur"] for d in lignes_dec if d["annees"] == 30 and d["p_star"] == ps and not math.isnan(d["valeur"])]
    sr = [d["part_serre"] for d in lignes_dec if d["annees"] == 30 and d["p_star"] == ps]
    print(f"{ps:>5.2f} {sum(v) / len(v) if v else float('nan'):>7.3f} {sum(sr) / len(sr):>11.3f}")
print(f"\nTerminé : analyse/backtest_scores{suffixe}.csv, backtest_fiabilite{suffixe}.csv, backtest_decisions{suffixe}.csv")
