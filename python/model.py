## salut
"""
MODÈLE — ta partie.
Tout le calcul statistique est ici. app.py ne fait qu'afficher.
"""
from datetime import date, timedelta
import math

WINDOW_DAYS = 7      # demi-largeur de la fenêtre climatologique (jours)
FORECAST_DAYS = 16   # horizon max de la prévision Open-Meteo
Z = 1.959964         # quantile normal 0.975 (sert au calcul du quantile de Student)


def same_day(year: int, month: int, day: int) -> date:
    """Même jour calendaire dans une autre année (29 février -> 1er mars)."""
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, 3, 1)


def climatology(hist: dict, month: int, day: int, thr: float, years: range, W: int = WINDOW_DAYS):
    """Pour chaque année y, compte les jours avec pluie >= thr dans la fenêtre W_y = ±W jours
    autour du même jour calendaire. hist : {date: précipitation en mm}.
    Renvoie la liste [(k_y, n_y), ...] (années sans aucune donnée omises)."""
    out = []
    for y in years:
        c = same_day(y, month, day)
        k = n = 0
        for o in range(-W, W + 1):
            v = hist.get(c + timedelta(days=o))
            if v is None:
                continue
            n += 1
            k += v >= thr
        if n > 0:
            out.append((k, n))
    return out


def daily_profile(hist: dict, month: int, day: int, thr: float, years: range, span: int = 30):
    """Fréquence de pluie jour par jour autour de la date (pour le graphique)."""
    out = []
    for o in range(-span, span + 1):
        k = n = 0
        for y in years:
            v = hist.get(same_day(y, month, day) + timedelta(days=o))
            if v is None:
                continue
            n += 1
            k += v >= thr
        out.append((o, k / n if n else 0.0))
    return out


def t_quantile(nu: int, z: float = Z) -> float:
    """Quantile de la loi de Student à nu degrés de liberté (développement de Cornish-Fisher,
    erreur < 1e-4 pour nu >= 5). Pour nu = 29 : 2.0452."""
    g1 = (z**3 + z) / 4
    g2 = (5 * z**5 + 16 * z**3 + 3 * z) / 96
    g3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / 384
    g4 = (79 * z**9 + 776 * z**7 + 1482 * z**5 - 1920 * z**3 - 945 * z) / 92160
    return z + g1 / nu + g2 / nu**2 + g3 / nu**3 + g4 / nu**4


def year_interval(years):
    """Note méthodologique, éq. (2), (3), (5) : l'année comme unité.
    p_y = k_y / n_y ; p_hat = moyenne des p_y ; s² = variance empirique (1/(Y-1)) ;
    IC 95 % = p_hat ± t_{Y-1; 0.975} · s / sqrt(Y), intersecté avec [0, 1]."""
    p_y = [k / n for k, n in years]
    Y = len(p_y)
    p_hat = sum(p_y) / Y
    s2 = sum((p - p_hat) ** 2 for p in p_y) / (Y - 1)
    half = t_quantile(Y - 1) * math.sqrt(s2 / Y)
    return p_hat, max(0.0, p_hat - half), min(1.0, p_hat + half), math.sqrt(s2), Y


def compute_risk(years, pf, h: int, R: float, lam: float, C: float) -> dict:
    """
    years : [(k_y, n_y), ...] jours de pluie / jours observés pour chaque année (climatologie)
    pf    : probabilité de précipitation prévue (0-1) ou None
    h     : jours avant l'événement
    R     : recette attendue (CHF), lam : part perdue s'il pleut (0-1), C : coût de la protection (CHF)
    """
    pc, lo, hi, s, Y = year_interval(years)                        # éq. (3) et (5)
    w = 0.0 if pf is None else max(0.0, 1 - h / FORECAST_DAYS)   # poids de la prévision, éq. (6)
    pf0 = pf or 0.0
    p = w * pf0 + (1 - w) * pc                                     # éq. (6)
    p_lo = w * pf0 + (1 - w) * lo                                  # éq. (7)
    p_hi = w * pf0 + (1 - w) * hi

    loss = lam * R                  # perte si pluie
    EL = p * loss                   # perte attendue, éq. (9)
    p_star = C / loss if loss > 0 else math.inf   # seuil de décision, éq. (11)

    if p_lo > p_star:               # éq. (12)
        decision = "protect"
    elif p_hi < p_star:
        decision = "skip"
    else:
        decision = "close"

    return dict(pc=pc, lo=lo, hi=hi, s=s, Y=Y, w=w, p=p, p_lo=p_lo, p_hi=p_hi,
                loss=loss, EL=EL, p_star=p_star, decision=decision)
