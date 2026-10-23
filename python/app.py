"""
Plan B - Weather Risk — interface Streamlit (FR / EN).
Lancer en local (depuis le dossier python/) :  streamlit run app.py
Le calcul est dans model.py.
"""
from datetime import date, timedelta
import math

import altair as alt
import pandas as pd
import requests
import streamlit as st

import model

st.set_page_config(page_title="Weather Risk Management", page_icon="🌧️", layout="wide")

N_YEARS = 30
Y1 = date.today().year - 1          # dernière année complète
YEARS = range(Y1 - N_YEARS + 1, Y1 + 1)

# ---------------------------------------------------------------- textes
TXT = {
    "fr": dict(
        eyebrow="Risque météo · événements en plein air",
        lede="Indiquez le lieu, la date et ce que la pluie vous coûterait. L'outil estime la probabilité de pluie "
             "à partir de 30 ans de données et de la prévision du moment, puis vous dit si une protection vaut son prix.",
        place="Lieu", place_help="Nom de la commune, sans le pays.",
        date="Date de l'événement", rev="Recette attendue (CHF)", lam="Perte si pluie (%)",
        thr="Seuil de pluie (mm)", cost="Coût de la protection (CHF)",
        cost_help="Tente, salle de repli ou assurance annulation.", go="Évaluer le risque",
        past="La date est passée. Choisissez une date à venir.",
        not_found="Lieu introuvable : « {} ». Essayez le nom d'une commune, sans le pays.",
        net="Impossible de joindre le service météo. Réessayez dans un instant.",
        no_data="Pas assez de données historiques pour ce lieu.",
        loading="Lecture de 30 ans de données pour {}…",
        summary="{} · {} (dans {} j) · {} jours de pluie sur {} dans l'historique",
        fc_note=" · prévision : {} %",
        protect=("Protéger", "La protection est rentable",
                 "Avec {p} de risque de pluie, la perte attendue ({el}) dépasse le coût de la protection ({c})."),
        skip=("Ne pas protéger", "La protection coûte plus qu'elle ne rapporte",
              "Avec {p} de risque de pluie, la perte attendue ({el}) reste sous le coût de la protection ({c})."),
        close=("Décision serrée", "Le seuil est dans la marge d'incertitude",
               "La probabilité se situe entre {lo} et {hi}, et le seuil de rentabilité est de {ps}. "
               "Le calcul {lean}, mais l'écart n'est pas significatif."),
        lean_up="penche vers la protection", lean_down="penche vers l'absence de protection",
        m_p="Probabilité de pluie", m_loss="Perte si pluie", m_el="Perte attendue", m_ps="Seuil de décision",
        range="{} à {}", fc_w=" · prévision {} %", clim=" · climatologie",
        of_rev="{} % de {}", prot="protection : {}", never="jamais rentable", above="protéger au-delà",
        chart_title="Fréquence historique de pluie autour de la date",
        chart_caption="Zone claire : fenêtre utilisée pour le calcul · trait plein : probabilité retenue · "
                      "trait rouge : seuil de décision",
        freq="Fréquence", day="Jour",
        method="Méthode et limites",
        m1="**Climatologie.** Sur les 30 dernières années complètes, on retient les jours situés à ±7 jours "
           "de la date visée, soit environ $n \\approx 450$ jours. Si $k$ d'entre eux dépassent le seuil :",
        m1b="avec un intervalle de Wilson à 95 %.",
        m2="**Prévision.** Si l'événement a lieu dans moins de 16 jours, on mélange la climatologie avec la "
           "probabilité de précipitation prévue $p_f$, où $h$ est le nombre de jours avant l'événement :",
        m3="**Décision.** La perte vaut $L = \\lambda R$ s'il pleut et $0$ sinon, donc "
           "$\\mathbb{E}[L] = p\\,\\lambda R$. La protection est rentable si :",
        m3b="Si $p^\\ast$ tombe dans l'intervalle d'incertitude de $p$, la décision est jugée serrée.",
        limits="**Limites.** Au-delà d'une à deux semaines, le résultat est de la climatologie et non une prévision. "
               "Les jours de la fenêtre sont corrélés entre eux, ce qui rend l'intervalle trop étroit. La prévision "
               "donne la probabilité d'une précipitation quelconque, pas celle de dépasser le seuil choisi. Les données "
               "sont des réanalyses sur une grille d'environ 10 à 25 km : un orage local peut leur échapper.",
        footer="Données météo : [Open-Meteo](https://open-meteo.com/) (réanalyse ERA5 et modèles de prévision). "
               "Outil d'aide à la décision, sans garantie.",
        months=["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
        pct_sep=" ",
    ),
    "en": dict(
        eyebrow="Weather risk · outdoor events",
        lede="Enter the location, the date and what rain would cost you. The tool estimates the chance of rain from "
             "30 years of data and the current forecast, then tells you whether protection is worth its price.",
        place="Location", place_help="Town name, without the country.",
        date="Event date", rev="Expected revenue (CHF)", lam="Loss if it rains (%)",
        thr="Rain threshold (mm)", cost="Cost of protection (CHF)",
        cost_help="Tent, indoor fallback venue or cancellation insurance.", go="Assess the risk",
        past="That date has passed. Pick a future date.",
        not_found='Location not found: "{}". Try a town name without the country.',
        net="Could not reach the weather service. Try again in a moment.",
        no_data="Not enough historical data for this location.",
        loading="Reading 30 years of data for {}…",
        summary="{} · {} (in {} days) · {} rainy days out of {} in the record",
        fc_note=" · forecast: {}%",
        protect=("Protect", "Protection pays off",
                 "With a {p} chance of rain, the expected loss ({el}) exceeds the cost of protection ({c})."),
        skip=("Don't protect", "Protection costs more than it saves",
              "With a {p} chance of rain, the expected loss ({el}) stays below the cost of protection ({c})."),
        close=("Close call", "The threshold is within the uncertainty",
               "The probability lies between {lo} and {hi}, and the break-even threshold is {ps}. "
               "The estimate {lean}, but the gap is not significant."),
        lean_up="leans towards protecting", lean_down="leans towards not protecting",
        m_p="Chance of rain", m_loss="Loss if it rains", m_el="Expected loss", m_ps="Decision threshold",
        range="{} to {}", fc_w=" · forecast {}%", clim=" · climatology",
        of_rev="{}% of {}", prot="protection: {}", never="never pays off", above="protect above this",
        chart_title="Historical rain frequency around the date",
        chart_caption="Shaded area: window used for the estimate · solid line: estimated probability · "
                      "red line: decision threshold",
        freq="Frequency", day="Day",
        method="Method and limitations",
        m1="**Climatology.** Over the last 30 complete years, we take the days within ±7 days of the target date, "
           "about $n \\approx 450$ days. If $k$ of them exceed the threshold:",
        m1b="with a 95% Wilson interval.",
        m2="**Forecast.** If the event is less than 16 days away, climatology is blended with the forecast "
           "probability of precipitation $p_f$, where $h$ is the number of days until the event:",
        m3="**Decision.** The loss is $L = \\lambda R$ if it rains and $0$ otherwise, so "
           "$\\mathbb{E}[L] = p\\,\\lambda R$. Protection pays off if:",
        m3b="If $p^\\ast$ falls inside the uncertainty interval of $p$, the decision is flagged as a close call.",
        limits="**Limitations.** Beyond one or two weeks, the result is climatology, not a forecast. Days within the "
               "window are correlated, so the interval is too narrow. The forecast gives the probability of any "
               "precipitation, not of exceeding the chosen threshold. The data are reanalyses on a grid of roughly "
               "10 to 25 km, so a local thunderstorm can be missed.",
        footer="Weather data: [Open-Meteo](https://open-meteo.com/) (ERA5 reanalysis and forecast models). "
               "Decision-support tool, provided without warranty.",
        months=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        pct_sep="",
    ),
}

# ---------------------------------------------------------------- langue (une URL par langue : ?lang=fr / ?lang=en)
lang = st.query_params.get("lang", "en")
if lang not in TXT:
    lang = "en"
T = TXT[lang]

head_l, head_r = st.columns([5, 1])
with head_r:
    choice = st.segmented_control("Langue / Language", ["FR", "EN"], default=lang.upper(),
                                  label_visibility="collapsed", key="lang_sel")
    if choice and choice.lower() != lang:
        st.query_params["lang"] = choice.lower()
        st.rerun()
with head_l:
    st.caption(T["eyebrow"].upper())
    st.title("Plan B - Weather Risk")
    st.write(T["lede"])


# ---------------------------------------------------------------- mise en forme
def chf(x: float) -> str:
    return "CHF " + f"{x:,.0f}".replace(",", "’")


def pct(x: float) -> str:
    v = f"{100 * x:.1f}" if x < 0.1 else f"{100 * x:.0f}"
    return v + T["pct_sep"] + "%"


def day_label(d: date) -> str:
    return f"{d.day} {T['months'][d.month - 1]}"


# ---------------------------------------------------------------- données Open-Meteo (sans clé)
@st.cache_data(ttl=7 * 86400, show_spinner=False)
def geocode(name: str, lang: str):
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params=dict(name=name, count=1, language=lang, format="json"), timeout=20)
    r.raise_for_status()
    res = r.json().get("results") or []
    return res[0] if res else None


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def fetch_history(lat: float, lon: float) -> dict:
    r = requests.get("https://archive-api.open-meteo.com/v1/archive", params=dict(
        latitude=lat, longitude=lon, start_date=f"{YEARS[0]}-01-01", end_date=f"{Y1}-12-31",
        daily="precipitation_sum", timezone="Europe/Zurich"), timeout=60)
    r.raise_for_status()
    d = r.json()["daily"]
    return {date.fromisoformat(t): v for t, v in zip(d["time"], d["precipitation_sum"]) if v is not None}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_forecast(lat: float, lon: float, day: date):
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=dict(
        latitude=lat, longitude=lon, daily="precipitation_probability_max,precipitation_sum",
        timezone="Europe/Zurich", forecast_days=model.FORECAST_DAYS), timeout=20)
    r.raise_for_status()
    d = r.json()["daily"]
    if day.isoformat() not in d["time"]:
        return None
    pp = d["precipitation_probability_max"][d["time"].index(day.isoformat())]
    return None if pp is None else pp / 100


# ---------------------------------------------------------------- formulaire + résultats
left, right = st.columns([1, 2], gap="large")

with left:
    with st.form("inputs"):
        place = st.text_input(T["place"], "Zurich", help=T["place_help"])
        ev_date = st.date_input(T["date"], date.today() + timedelta(days=10), format="DD.MM.YYYY")
        R = st.number_input(T["rev"], min_value=0, value=20000, step=500)
        c1, c2 = st.columns(2)
        lam = c1.number_input(T["lam"], min_value=0, max_value=100, value=60, step=5)
        thr = c2.number_input(T["thr"], min_value=0.1, value=2.0, step=0.5)
        C = st.number_input(T["cost"], min_value=0, value=2500, step=100, help=T["cost_help"])
        st.form_submit_button(T["go"], type="primary", width="stretch")

with right:
    h = (ev_date - date.today()).days
    if h < 0:
        st.error(T["past"])
        st.stop()
    try:
        loc = geocode(place.strip(), lang)
        if loc is None:
            st.error(T["not_found"].format(place))
            st.stop()
        with st.spinner(T["loading"].format(loc["name"])):
            hist = fetch_history(loc["latitude"], loc["longitude"])
            pf = fetch_forecast(loc["latitude"], loc["longitude"], ev_date) if h < model.FORECAST_DAYS else None
    except requests.RequestException:
        st.error(T["net"])
        st.stop()

    k, n = model.climatology(hist, ev_date.month, ev_date.day, thr, YEARS)
    if n < 30:
        st.error(T["no_data"])
        st.stop()
    r = model.compute_risk(k, n, pf, h, R, lam / 100, C)

    where = ", ".join(x for x in [loc.get("name"), loc.get("admin1"), loc.get("country")] if x)
    st.caption(T["summary"].format(where, day_label(ev_date), h, k, n)
               + (T["fc_note"].format(round(pf * 100)) if pf is not None else ""))

    # verdict
    if r["decision"] == "close":
        tag, title, text = T["close"]
        text = text.format(lo=pct(r["p_lo"]), hi=pct(r["p_hi"]), ps=pct(r["p_star"]),
                           lean=T["lean_up"] if r["p"] > r["p_star"] else T["lean_down"])
        box = st.warning
    else:
        tag, title, text = T[r["decision"]]
        text = text.format(p=pct(r["p"]), el=chf(r["EL"]), c=chf(C))
        box = st.error if r["decision"] == "protect" else st.success
    box(f"**{tag.upper()}** — {title}\n\n{text}")

    # chiffres clés
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(T["m_p"], pct(r["p"]))
    m1.caption(T["range"].format(pct(r["p_lo"]), pct(r["p_hi"]))
               + (T["fc_w"].format(round(100 * r["w"])) if r["w"] > 0 else T["clim"]))
    m2.metric(T["m_loss"], chf(r["loss"]))
    m2.caption(T["of_rev"].format(lam, chf(R)))
    m3.metric(T["m_el"], chf(r["EL"]))
    m3.caption(T["prot"].format(chf(C)))
    m4.metric(T["m_ps"], pct(min(r["p_star"], 1)) if math.isfinite(r["p_star"]) else "—")
    m4.caption(T["never"] if r["p_star"] > 1 else T["above"])

# ---------------------------------------------------------------- graphique
st.subheader(T["chart_title"])
prof = pd.DataFrame(model.daily_profile(hist, ev_date.month, ev_date.day, thr, YEARS),
                    columns=["offset", "freq"])
prof["date"] = [pd.Timestamp(ev_date + timedelta(days=int(o))) for o in prof["offset"]]
prof["window"] = prof["offset"].abs() <= model.WINDOW_DAYS
prof["label"] = [day_label(d.date()) for d in prof["date"]]

win = pd.DataFrame({"start": [pd.Timestamp(ev_date - timedelta(days=model.WINDOW_DAYS, hours=12))],
                    "end": [pd.Timestamp(ev_date + timedelta(days=model.WINDOW_DAYS, hours=12))]})
band = alt.Chart(win).mark_rect(opacity=0.12, color="#1f77b4").encode(x="start:T", x2="end:T")
bars = alt.Chart(prof).mark_bar(color="#1f5f8b").encode(
    x=alt.X("date:T", title=T["day"], axis=alt.Axis(format="%d.%m")),
    y=alt.Y("freq:Q", title=T["freq"], axis=alt.Axis(format="%")),
    opacity=alt.condition("datum.window", alt.value(1.0), alt.value(0.35)),
    tooltip=[alt.Tooltip("label:N", title=T["day"]), alt.Tooltip("freq:Q", title=T["freq"], format=".0%")],
)
lines = [alt.Chart(pd.DataFrame({"y": [r["p"]]})).mark_rule(strokeWidth=2).encode(y="y:Q")]
if math.isfinite(r["p_star"]) and r["p_star"] <= 1:
    lines.append(alt.Chart(pd.DataFrame({"y": [r["p_star"]]}))
                 .mark_rule(color="#c0392b", strokeDash=[6, 4], strokeWidth=2).encode(y="y:Q"))
st.altair_chart(alt.layer(band, bars, *lines).properties(height=280), width="stretch")
st.caption(T["chart_caption"])

# ---------------------------------------------------------------- méthode : uniquement dans le PDF
# Le PDF est publié avec le site statique (dossier docs/, GitHub Pages)
# et s'ouvre dans un nouvel onglet avec le lecteur PDF du navigateur.
PDF_URL = "https://doriangirod.github.io/plan-b/rain-model.pdf"
DOC_BTN = "📄 Méthodologie (PDF)" if lang == "fr" else "📄 Methodology (PDF)"

st.divider()
foot_l, foot_r = st.columns([4, 1], vertical_alignment="center")
foot_l.caption(T["footer"])
foot_r.link_button(DOC_BTN, PDF_URL, width="stretch")
