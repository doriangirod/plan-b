"""
Comparaison des intervalles de confiance de Plan B (sans toucher au site).

  Ancienne méthode : jours i.i.d. -> binomiale, p_hat = k/n, intervalle de Wilson (n ~ 450).
  Nouvelle méthode : années i.i.d. -> p_hat = moyenne des p_hat_y, TCL, intervalle en t
                     p_hat +- t_{29;0.975} * s / sqrt(30), tronqué à [0, 1].

Lancer depuis le dossier Plan B :   .venv/bin/python analyse/comparer_intervalles.py
Résultats : affichés + enregistrés dans analyse/comparaison.csv
"""
import csv, json, math, os, time
from datetime import date, timedelta
import requests

VILLES = {            # nom: (lat, lon)
    "Zurich":   (47.37, 8.55),
    "Genève":   (46.20, 6.15),
    "Lugano":   (46.00, 8.95),
    "Sion":     (46.23, 7.36),
    "Bâle":     (47.56, 7.59),
    "Séville":  (37.39, -5.98),   # climat sec en été : petits p
}
DATES = [(1, 15), (4, 15), (7, 15), (10, 15)]   # (mois, jour)
SEUILS = [2.0, 10.0]                              # mm
W, NY = 7, 30
Y1 = date.today().year - 1
Y0 = Y1 - NY + 1
Z, T29 = 1.959964, 2.045230
SCENARIO = dict(R=20000, lam=0.60, C=2500)        # exemple par défaut du site
P_STAR = SCENARIO["C"] / (SCENARIO["lam"] * SCENARIO["R"])   # 0.208


SESSION = requests.Session()          # réutilise la connexion (moins de poignées de main TLS)
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE, exist_ok=True)


def telecharger(url):
    """GET avec plusieurs essais : attend de plus en plus longtemps en cas de lenteur, coupure ou quota."""
    for essai in range(8):
        try:
            r = SESSION.get(url, timeout=(10, 60))
            if r.status_code == 429:
                print("   quota atteint, pause 60 s ...", flush=True); time.sleep(60); continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            attente = min(5 * 2 ** essai, 120)
            print(f"   problème réseau ({type(e).__name__}), nouvel essai dans {attente} s ...", flush=True)
            time.sleep(attente)
    raise RuntimeError("Open-Meteo ne répond pas. Relance le script plus tard : il reprendra où il s'est arrêté.")


def fenetre(lat, lon, m, d):
    """Pluie journalière des 15 jours autour de (m, d), pour chaque année : {année: [mm, ...]}.
    Le résultat est gardé dans analyse/cache/ : relancer le script ne retélécharge pas."""
    fichier = os.path.join(CACHE, f"{lat}_{lon}_{m:02d}-{d:02d}_{Y0}-{Y1}.json")
    if os.path.exists(fichier):
        with open(fichier, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    out = {}
    for y in range(Y0, Y1 + 1):
        c = date(y, m, d)
        s, e = c - timedelta(days=W), c + timedelta(days=W)
        url = ("https://archive-api.open-meteo.com/v1/archive"
               f"?latitude={lat}&longitude={lon}&start_date={s}&end_date={e}"
               "&daily=precipitation_sum&timezone=Europe%2FZurich")
        j = telecharger(url)
        out[y] = [v for v in j["daily"]["precipitation_sum"] if v is not None]
        time.sleep(0.15)   # reste sous 600 appels / minute
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def wilson(ph, n):
    den = 1 + Z * Z / n
    c = (ph + Z * Z / (2 * n)) / den
    h = Z / den * math.sqrt(ph * (1 - ph) / n + Z * Z / (4 * n * n))
    return c - h, c + h


def verdict(lo, hi, ps):
    return "Protéger" if lo > ps else ("Ne pas protéger" if hi < ps else "Serré")


lignes = []
for ville, (lat, lon) in VILLES.items():
    for (m, d) in DATES:
        print(f"Téléchargement {ville} {d:02d}.{m:02d} ...", flush=True)
        data = fenetre(lat, lon, m, d)
        for t in SEUILS:
            ky = [sum(v >= t for v in data[y]) for y in data]
            ny = [len(data[y]) for y in data]
            k, n = sum(ky), sum(ny)
            # ancienne méthode
            p_old = k / n
            w_lo, w_hi = wilson(p_old, n)
            # nouvelle méthode
            py = [a / b for a, b in zip(ky, ny)]
            Y = len(py)
            p_new = sum(py) / Y
            s = math.sqrt(sum((x - p_new) ** 2 for x in py) / (Y - 1))
            n_lo = max(0.0, p_new - T29 * s / math.sqrt(Y))
            n_hi = min(1.0, p_new + T29 * s / math.sqrt(Y))
            lignes.append(dict(
                ville=ville, date=f"{d:02d}.{m:02d}", seuil_mm=t, n=n, k=k,
                p_ancien=round(p_old, 4), wilson_bas=round(w_lo, 4), wilson_haut=round(w_hi, 4),
                p_nouveau=round(p_new, 4), tcl_bas=round(n_lo, 4), tcl_haut=round(n_hi, 4),
                rapport_largeur=round((n_hi - n_lo) / (w_hi - w_lo), 2) if w_hi > w_lo else None,
                verdict_ancien=verdict(w_lo, w_hi, P_STAR), verdict_nouveau=verdict(n_lo, n_hi, P_STAR),
            ))

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "comparaison.csv"), "w", newline="", encoding="utf-8") as f:
    wr = csv.DictWriter(f, fieldnames=list(lignes[0]))
    wr.writeheader(); wr.writerows(lignes)

print(f"\nSeuil de rentabilité de l'exemple : p* = {P_STAR:.3f}\n")
print(f"{'ville':8} {'date':5} {'t':>4} | {'p ancien':>8} {'Wilson':>15} | {'p nouv.':>7} {'années+TCL':>15} | {'x larg.':>7} | verdicts")
for L in lignes:
    print(f"{L['ville']:8} {L['date']:5} {L['seuil_mm']:>4.0f} | {L['p_ancien']:>8.3f} [{L['wilson_bas']:.3f}, {L['wilson_haut']:.3f}] | "
          f"{L['p_nouveau']:>7.3f} [{L['tcl_bas']:.3f}, {L['tcl_haut']:.3f}] | {L['rapport_largeur'] or 0:>7.2f} | "
          f"{L['verdict_ancien']} -> {L['verdict_nouveau']}")
print("\nTerminé : analyse/comparaison.csv")
