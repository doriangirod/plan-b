"""
MODÈLE — ta partie.
Tout le calcul statistique est ici. app.py ne fait qu'afficher.
"""
from datetime import date, timedelta
import math

WINDOW_DAYS = 7      # demi-largeur de la fenêtre climatologique (jours)
FORECAST_DAYS = 16   # horizon max de la prévision Open-Meteo
Z = 1.96             # quantile pour l'intervalle à 95 %


def same_day(year: int, month: int, day: int) -> date:
    """Même jour calendaire dans une autre année (29 février -> 1er mars)."""
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, 3, 1)


def climatology(hist: dict, month: int, day: int, thr: float, years: range, W: int = WINDOW_DAYS):
    """Compte les jours avec pluie >= thr dans la fenêtre ±W autour du même jour, chaque année.
    hist : {date: précipitation en mm}. Renvoie (k, n)."""
    k = n = 0
    for y in years:
        c = same_day(y, month, day)
        for o in range(-W, W + 1):
            v = hist.get(c + timedelta(days=o))
            if v is None:
                continue
            n += 1
            k += v >= thr
    return k, n


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


def wilson(k: int, n: int, z: float = Z):
    p, z2 = k / n, z * z
    den = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / den
    half = (z / den) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def compute_risk(k: int, n: int, pf, h: int, R: float, lam: float, C: float) -> dict:
    """
    k, n : jours de pluie / jours observés (climatologie)
    pf   : probabilité de précipitation prévue (0-1) ou None
    h    : jours avant l'événement
    R    : recette attendue (CHF), lam : part perdue s'il pleut (0-1), C : coût de la protection (CHF)
    """
    pc = k / n
    lo, hi = wilson(k, n)
    w = 0.0 if pf is None else max(0.0, 1 - h / FORECAST_DAYS)   # poids de la prévision
    pf0 = pf or 0.0
    p = w * pf0 + (1 - w) * pc
    p_lo = w * pf0 + (1 - w) * lo
    p_hi = w * pf0 + (1 - w) * hi

    loss = lam * R                  # perte si pluie
    EL = p * loss                   # perte attendue
    p_star = C / loss if loss > 0 else math.inf   # seuil de décision

    if p_lo > p_star:
        decision = "protect"
    elif p_hi < p_star:
        decision = "skip"
    else:
        decision = "close"

    return dict(pc=pc, lo=lo, hi=hi, w=w, p=p, p_lo=p_lo, p_hi=p_hi,
                loss=loss, EL=EL, p_star=p_star, decision=decision)
