"""
Lever et coucher du soleil, calculés hors ligne (algorithme de la NOAA,
précis à une ou deux minutes près en France). Sert au thème « Selon le
soleil » : clair le jour, nuit dès le coucher du soleil.

Par défaut : L'Isle-sur-la-Sorgue (Vaucluse). Le lieu se change dans
Réglages > Apparence (latitude, longitude).
"""

import math
from datetime import date, datetime, timedelta

LIEU_PAR_DEFAUT = (43.9194, 5.0511)     # L'Isle-sur-la-Sorgue


def _fuseau_paris(jour):
    """Décalage de l'heure de Paris (UTC+1 l'hiver, UTC+2 l'été) pour ce jour."""
    def dernier_dimanche(annee, mois):
        d = date(annee, mois, 31)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    ete = dernier_dimanche(jour.year, 3) <= jour < dernier_dimanche(jour.year, 10)
    return timedelta(hours=2 if ete else 1)


def lever_coucher(jour=None, lat=None, lon=None, decalage=None):
    """(lever, coucher) en heure locale (datetime naïfs). None, None au-delà du cercle polaire."""
    jour = jour or date.today()
    lat = LIEU_PAR_DEFAUT[0] if lat is None else lat
    lon = LIEU_PAR_DEFAUT[1] if lon is None else lon
    decalage = _fuseau_paris(jour) if decalage is None else decalage
    n = jour.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (n - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    phi = math.radians(lat)
    cos_h = (math.cos(math.radians(90.833)) / (math.cos(phi) * math.cos(decl))) - math.tan(phi) * math.tan(decl)
    if cos_h < -1 or cos_h > 1:
        return None, None
    ha = math.degrees(math.acos(cos_h))
    minuit = datetime(jour.year, jour.month, jour.day)

    def heure(minutes_utc):
        return minuit + timedelta(minutes=minutes_utc) + decalage

    return heure(720 - 4 * (lon + ha) - eqtime), heure(720 - 4 * (lon - ha) - eqtime)


def fait_jour(maintenant=None, lat=None, lon=None):
    maintenant = maintenant or datetime.now()
    lever, coucher = lever_coucher(maintenant.date(), lat, lon)
    if lever is None:
        return maintenant.month in (4, 5, 6, 7, 8, 9)
    return lever <= maintenant < coucher


def prochain_changement(maintenant=None, lat=None, lon=None):
    """Datetime du prochain lever ou coucher (pour programmer la bascule du thème)."""
    maintenant = maintenant or datetime.now()
    for j in range(0, 3):
        lever, coucher = lever_coucher(maintenant.date() + timedelta(days=j), lat, lon)
        for t in (lever, coucher):
            if t and t > maintenant:
                return t
    return maintenant + timedelta(hours=12)


def texte_heure(dt):
    return f"{dt.hour} h {dt.minute:02d}" if dt else "—"
