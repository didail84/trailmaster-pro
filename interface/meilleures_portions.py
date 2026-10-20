"""
Meilleures portions et secteurs d'une sortie.

À partir de la trace GPS d'une sortie (points avec temps et, si dispo,
FC), calcule :
  - les MEILLEURES PORTIONS : le plus rapide 400 m, 1 km, 5 km, 10 km…
    et la meilleure vitesse tenue sur 5, 10, 20, 30, 60 minutes ;
  - les SECTEURS kilomètre par kilomètre (allure, pente, D+, FC) ;
  - le TERRAIN : allure en montée, sur le plat et en descente.

Le temps compté est le temps en mouvement : une pause (écart de plus
de 30 s entre deux points) n'est pas comptée, et ne peut donc pas fausser
une « meilleure » portion. Les vitesses impossibles (saut GPS) sont
écartées.

L'écran affiche le tracé coloré selon l'allure locale (vert = rapide,
rouge = lent) et surligne la portion choisie dans les tableaux.
100 % local, aucune dépendance réseau.
"""

import bisect
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF, QLinearGradient, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QAbstractItemView,
)

from interface.gpx_utils import _distance_haversine_km
from interface.survol_graphique import dessiner_infobulle

ECART_MAX_S = 30                       # au-delà : pause / coupure, non comptée
DISTANCES_KM = [0.4, 1, 2, 5, 10, 15, 21.0975, 30, 42.195]
DUREES_MIN = [5, 10, 20, 30, 60]
SEUIL_PENTE_PCT = 4.0                  # montée > +4 %, descente < -4 %
VITESSE_MAX_COURSE_KMH = 30
VITESSE_MAX_VELO_KMH = 70


# ------------------------------------------------------------------
# Mise en forme
# ------------------------------------------------------------------

def formater_allure(minutes_par_km):
    if not minutes_par_km or minutes_par_km <= 0 or math.isinf(minutes_par_km):
        return "—"
    total = int(round(minutes_par_km * 60))
    return f"{total // 60}:{total % 60:02d} /km"


def formater_duree(secondes):
    total = int(round(secondes))
    h, reste = divmod(total, 3600)
    m, s = divmod(reste, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ------------------------------------------------------------------
# Préparation de la trace
# ------------------------------------------------------------------

class Trace:
    """Trace nettoyée : distances et temps en mouvement cumulés."""

    def __init__(self, points):
        pts = [p for p in points if len(p) >= 4 and p[3] is not None]
        pts.sort(key=lambda p: p[3])
        self.points = pts
        n = len(pts)
        self.dist = [0.0] * n      # mètres cumulés
        self.temps = [0.0] * n     # secondes en mouvement cumulées
        for i in range(1, n):
            a, b = pts[i - 1], pts[i]
            dt = b[3] - a[3]
            d = _distance_haversine_km(a[0], a[1], b[0], b[1]) * 1000
            self.dist[i] = self.dist[i - 1] + d
            ajout = dt if 0 < dt <= ECART_MAX_S else 0.0
            self.temps[i] = self.temps[i - 1] + ajout
            if ajout == 0.0 and dt > ECART_MAX_S:
                # pause : la distance parcourue pendant la coupure n'est pas
                # attribuée à du temps en mouvement
                self.dist[i] = self.dist[i - 1]
        self.alt = [p[2] if len(p) > 2 and p[2] is not None else 0.0 for p in pts]
        self.fc = [p[4] if len(p) > 4 and p[4] else None for p in pts]

    @property
    def utilisable(self):
        return (len(self.points) >= 20 and self.dist[-1] >= 400
                and self.temps[-1] >= 120)

    def _interp(self, tableau_cum, cible):
        """Indice fractionnaire où tableau_cum atteint `cible`."""
        i = bisect.bisect_left(tableau_cum, cible)
        if i <= 0:
            return 0.0
        if i >= len(tableau_cum):
            return float(len(tableau_cum) - 1)
        a, b = tableau_cum[i - 1], tableau_cum[i]
        return (i - 1) + ((cible - a) / (b - a) if b > a else 0.0)

    def valeur_a(self, tableau, x):
        """Valeur interpolée de `tableau` à l'indice fractionnaire x."""
        i = int(math.floor(x))
        if i >= len(tableau) - 1:
            return tableau[-1]
        f = x - i
        return tableau[i] + (tableau[i + 1] - tableau[i]) * f

    def stats(self, x0, x1):
        """Statistiques entre deux indices fractionnaires."""
        d = self.valeur_a(self.dist, x1) - self.valeur_a(self.dist, x0)
        t = self.valeur_a(self.temps, x1) - self.valeur_a(self.temps, x0)
        i0, i1 = int(math.ceil(x0)), int(math.floor(x1))
        gain = perte = 0.0
        for k in range(i0 + 1, i1 + 1):
            diff = self.alt[k] - self.alt[k - 1]
            if diff > 0.5:
                gain += diff
            elif diff < -0.5:
                perte -= diff
        fcs = [self.fc[k] for k in range(i0, i1 + 1) if self.fc[k]]
        return {
            "distance_m": d, "duree_s": t,
            "allure": (t / 60) / (d / 1000) if d > 0 else None,
            "vitesse_kmh": d / t * 3.6 if t > 0 else None,
            "d_plus": round(gain), "d_moins": round(perte),
            "fc_moy": round(sum(fcs) / len(fcs)) if fcs else None,
            "pente_pct": ((self.valeur_a(self.alt, x1) - self.valeur_a(self.alt, x0)) / d * 100)
            if d > 0 else 0.0,
        }

    def vitesses_locales(self, demi_fenetre_m=50):
        """Vitesse (km/h) en chaque point, sur ±50 m (lisse le bruit GPS)."""
        n = len(self.points)
        resultat = []
        for i in range(n):
            a = bisect.bisect_left(self.dist, self.dist[i] - demi_fenetre_m)
            b = min(bisect.bisect_right(self.dist, self.dist[i] + demi_fenetre_m) - 1, n - 1)
            dt = self.temps[b] - self.temps[a]
            dd = self.dist[b] - self.dist[a]
            resultat.append(dd / dt * 3.6 if dt > 0 and dd > 0 else None)
        return resultat


# ------------------------------------------------------------------
# Calculs
# ------------------------------------------------------------------

def _label_distance(km):
    if abs(km - 21.0975) < 0.01:
        return "Semi-marathon (21,1 km)"
    if abs(km - 42.195) < 0.01:
        return "Marathon (42,2 km)"
    if km < 1:
        return f"{int(km * 1000)} m"
    return f"{km:g} km".replace(".", ",")


def meilleures_portions(trace, type_sortie=""):
    """Liste de portions : les plus rapides sur des distances données,
    puis les meilleures vitesses tenues sur des durées données."""
    vmax = VITESSE_MAX_VELO_KMH if type_sortie in ("Vélo", "VTT") else VITESSE_MAX_COURSE_KMH
    n = len(trace.points)
    resultats = []

    # --- par distance : on cherche le plus petit temps
    for km in DISTANCES_KM:
        D = km * 1000
        if D > trace.dist[-1] * 0.98:
            continue
        meilleur = None
        j = 0
        for i in range(n):
            cible = trace.dist[i] + D
            if cible > trace.dist[-1]:
                break
            x_fin = trace._interp(trace.dist, cible)
            t = trace.valeur_a(trace.temps, x_fin) - trace.temps[i]
            if t <= 0 or D / t * 3.6 > vmax:
                continue
            if meilleur is None or t < meilleur[0]:
                meilleur = (t, float(i), x_fin)
        if meilleur:
            resultats.append(_portion(trace, f"Plus rapide : {_label_distance(km)}",
                                      meilleur[1], meilleur[2], "distance"))

    # --- par durée : on cherche la plus grande distance
    for minutes in DUREES_MIN:
        T = minutes * 60
        if T > trace.temps[-1] * 0.98:
            continue
        meilleur = None
        for i in range(n):
            cible = trace.temps[i] + T
            if cible > trace.temps[-1]:
                break
            x_fin = trace._interp(trace.temps, cible)
            d = trace.valeur_a(trace.dist, x_fin) - trace.dist[i]
            if d <= 0 or d / T * 3.6 > vmax:
                continue
            if meilleur is None or d > meilleur[0]:
                meilleur = (d, float(i), x_fin)
        if meilleur:
            resultats.append(_portion(trace, f"Meilleurs {minutes} min",
                                      meilleur[1], meilleur[2], "duree"))
    return resultats


def _portion(trace, libelle, x0, x1, genre):
    s = trace.stats(x0, x1)
    s.update({
        "libelle": libelle, "genre": genre, "x0": x0, "x1": x1,
        "debut_km": trace.valeur_a(trace.dist, x0) / 1000,
        "fin_km": trace.valeur_a(trace.dist, x1) / 1000,
    })
    return s


def secteurs_km(trace, longueur_m=1000):
    """Un secteur par kilomètre (le dernier, partiel, s'il fait ≥ 200 m)."""
    secteurs = []
    total = trace.dist[-1]
    debut = 0.0
    numero = 1
    while debut < total:
        fin = min(debut + longueur_m, total)
        if fin - debut < 200 and numero > 1:
            break
        x0 = trace._interp(trace.dist, debut)
        x1 = trace._interp(trace.dist, fin)
        s = trace.stats(x0, x1)
        if s["duree_s"] > 0:
            s.update({"libelle": f"Km {numero}" if fin - debut >= longueur_m - 1
                      else f"Dernier ({(fin - debut) / 1000:.2f} km)".replace(".", ","),
                      "x0": x0, "x1": x1, "debut_km": debut / 1000, "fin_km": fin / 1000})
            secteurs.append(s)
        debut = fin
        numero += 1
    return secteurs


def repartition_terrain(trace, pas_m=200):
    """Montée / plat / descente : distance, temps, allure moyenne."""
    cumul = {"Montée": [0.0, 0.0], "Plat": [0.0, 0.0], "Descente": [0.0, 0.0]}
    total = trace.dist[-1]
    debut = 0.0
    while debut + pas_m <= total + 1:
        fin = min(debut + pas_m, total)
        x0 = trace._interp(trace.dist, debut)
        x1 = trace._interp(trace.dist, fin)
        s = trace.stats(x0, x1)
        if s["duree_s"] > 0 and s["distance_m"] > 0:
            if s["pente_pct"] > SEUIL_PENTE_PCT:
                cat = "Montée"
            elif s["pente_pct"] < -SEUIL_PENTE_PCT:
                cat = "Descente"
            else:
                cat = "Plat"
            cumul[cat][0] += s["distance_m"]
            cumul[cat][1] += s["duree_s"]
        debut = fin
        if fin >= total:
            break
    lignes = []
    for cat, (d, t) in cumul.items():
        if d > 0:
            lignes.append({
                "libelle": cat, "distance_m": d, "duree_s": t,
                "allure": (t / 60) / (d / 1000), "vitesse_kmh": d / t * 3.6,
            })
    return lignes


# ------------------------------------------------------------------
# Carte (tracé coloré par allure)
# ------------------------------------------------------------------

def _couleur_vitesse(ratio):
    """ratio 0 = lent (rouge) → 1 = rapide (vert), via le jaune."""
    ratio = max(0.0, min(1.0, ratio))
    if ratio < 0.5:
        r, g = 229, int(57 + (193 - 57) * (ratio / 0.5))
    else:
        r, g = int(229 - (229 - 67) * ((ratio - 0.5) / 0.5)), int(193 + (160 - 193) * ((ratio - 0.5) / 0.5))
    return QColor(r, g, 53 if ratio < 0.5 else 71)


class CarteVitesse(QWidget):
    """Tracé hors-ligne coloré selon l'allure locale, avec une portion
    surlignée et une info-bulle au survol."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trace = None
        self.vitesses = []
        self.surlignage = None        # (x0, x1) indices fractionnaires
        self._survol = None
        self._geo = None
        self.setMinimumHeight(300)
        self.setMouseTracking(True)

    def definir(self, trace):
        self.trace = trace
        self.vitesses = trace.vitesses_locales()
        valides = sorted(v for v in self.vitesses if v)
        if valides:
            self._v_bas = valides[int(len(valides) * 0.05)]
            self._v_haut = valides[min(int(len(valides) * 0.95), len(valides) - 1)]
        else:
            self._v_bas, self._v_haut = 0.0, 1.0
        self.surlignage = None
        self.update()

    def surligner(self, x0, x1):
        self.surlignage = (x0, x1)
        self.update()

    def _preparer_geo(self):
        pts = self.trace.points
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        lat0, lat1, lon0, lon1 = min(lats), max(lats), min(lons), max(lons)
        cos = math.cos(math.radians((lat0 + lat1) / 2))
        marge = 28
        largeur = max(self.width() - 2 * marge, 10)
        hauteur = max(self.height() - 2 * marge - 14, 10)
        w_geo = max((lon1 - lon0) * cos, 1e-6)
        h_geo = max(lat1 - lat0, 1e-6)
        k = min(largeur / w_geo, hauteur / h_geo)
        # on corrige la longitude par cos(lat) pour garder les proportions
        self._geo = {
            "x": marge + (largeur - w_geo * k) / 2, "y": marge + (hauteur - h_geo * k) / 2,
            "lon0": lon0, "lat1": lat1, "k": k, "cos": cos,
        }

    def _px(self, lat, lon):
        g = self._geo
        return QPointF(g["x"] + (lon - g["lon0"]) * g["cos"] * g["k"],
                       g["y"] + (g["lat1"] - lat) * g["k"])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#15191D"))
        if not self.trace or len(self.trace.points) < 2:
            painter.end()
            return
        self._preparer_geo()
        pts = self.trace.points
        px = [self._px(p[0], p[1]) for p in pts]

        # contour sombre pour la lisibilité
        painter.setPen(QPen(QColor("#0B0E10"), 7, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPolyline(QPolygonF(px))

        etendue = max(self._v_haut - self._v_bas, 0.01)
        for i in range(1, len(px)):
            v = self.vitesses[i] or self.vitesses[i - 1]
            ratio = (v - self._v_bas) / etendue if v else 0.0
            painter.setPen(QPen(_couleur_vitesse(ratio), 4, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(px[i - 1], px[i])

        # portion surlignée
        if self.surlignage:
            x0, x1 = self.surlignage
            i0, i1 = int(math.ceil(x0)), int(math.floor(x1))
            sous = [px[max(i0 - 1, 0)] if i0 > 0 else px[0]] + px[i0:i1 + 1]
            if len(sous) >= 2:
                painter.setPen(QPen(QColor("#FFFFFF"), 9, Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.drawPolyline(QPolygonF(sous))
                for i in range(max(i0, 1), i1 + 1):
                    v = self.vitesses[i] or self.vitesses[i - 1]
                    ratio = (v - self._v_bas) / etendue if v else 0.0
                    painter.setPen(QPen(_couleur_vitesse(ratio), 5, Qt.PenStyle.SolidLine,
                                        Qt.PenCapStyle.RoundCap))
                    painter.drawLine(px[i - 1], px[i])
                painter.setPen(QPen(QColor("#15191D"), 2))
                painter.setBrush(QColor("#42A5F5"))
                painter.drawEllipse(sous[0], 7, 7)
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawEllipse(sous[-1], 7, 7)
                painter.setPen(QColor("#FFFFFF"))
                f = QFont(painter.font())
                f.setBold(True)
                painter.setFont(f)
                painter.drawText(QPointF(sous[0].x() + 10, sous[0].y() - 8), "début")
                painter.drawText(QPointF(sous[-1].x() + 10, sous[-1].y() - 8), "fin")

        # départ
        painter.setPen(QPen(QColor("#15191D"), 2))
        painter.setBrush(QColor("#43A047"))
        painter.drawEllipse(px[0], 5, 5)

        # légende : dégradé lent → rapide
        self._dessiner_legende(painter)

        # info-bulle au survol
        if self._survol is not None:
            i = self._survol
            p = px[i]
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.setBrush(QColor("#15191D"))
            painter.drawEllipse(p, 6, 6)
            v = self.vitesses[i]
            lignes = [(None, f"Km {self.trace.dist[i] / 1000:.2f}".replace(".", ","))]
            if v:
                lignes.append((None, f"Allure : {formater_allure(60 / v)}"))
                lignes.append((None, f"Vitesse : {v:.1f} km/h"))
            lignes.append((None, f"Altitude : {round(self.trace.alt[i])} m"))
            if self.trace.fc[i]:
                lignes.append((None, f"FC : {round(self.trace.fc[i])} bpm"))
            dessiner_infobulle(painter, QRectF(self.rect()), p.x(), p.y(), "Ici", lignes)
        painter.end()

    def _dessiner_legende(self, painter):
        w = 160
        x = self.width() - w - 14
        y = self.height() - 22
        degrade = QLinearGradient(x, 0, x + w, 0)
        degrade.setColorAt(0.0, _couleur_vitesse(0))
        degrade.setColorAt(0.5, _couleur_vitesse(0.5))
        degrade.setColorAt(1.0, _couleur_vitesse(1))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(degrade)
        painter.drawRoundedRect(QRectF(x, y, w, 8), 4, 4)
        painter.setPen(QColor("#9AA3AA"))
        painter.drawText(QPointF(x, y - 4), "lent")
        painter.drawText(QPointF(x + w - 38, y - 4), "rapide")

    def mouseMoveEvent(self, event):
        if not self.trace or not self._geo:
            return
        pos = event.position()
        meilleur, dmin = None, 18 ** 2
        for i, p in enumerate(self.trace.points):
            q = self._px(p[0], p[1])
            d = (q.x() - pos.x()) ** 2 + (q.y() - pos.y()) ** 2
            if d < dmin:
                meilleur, dmin = i, d
        if meilleur != self._survol:
            self._survol = meilleur
            self.update()

    def leaveEvent(self, event):
        if self._survol is not None:
            self._survol = None
            self.update()


# ------------------------------------------------------------------
# Fenêtre
# ------------------------------------------------------------------

class DialogueMeilleuresPortions(QDialog):

    def __init__(self, points, titre_sortie="", type_sortie="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Meilleures portions — {titre_sortie}" if titre_sortie
                            else "Meilleures portions")
        self.resize(1000, 820)
        self.trace = Trace(points)

        layout = QVBoxLayout(self)
        titre = QLabel("🏅 Meilleures portions et secteurs")
        titre.setObjectName("titreCarte")
        layout.addWidget(titre)

        if not self.trace.utilisable:
            layout.addWidget(QLabel(
                "Cette sortie n'a pas assez de données horodatées (trace GPS avec le "
                "temps de chaque point) pour calculer des portions."))
            return

        self.carte = CarteVitesse()
        self.carte.definir(self.trace)
        layout.addWidget(self.carte, 3)

        aide = QLabel("Clique sur une ligne d'un tableau pour voir la portion sur la carte. "
                      "Le tracé est coloré selon ton allure (vert = rapide, rouge = lent) ; "
                      "survole-le pour lire l'allure en chaque point. Le temps compté est le "
                      "temps en mouvement (pauses exclues).")
        aide.setWordWrap(True)
        aide.setObjectName("texteDetail")
        layout.addWidget(aide)

        self.onglets = QTabWidget()
        layout.addWidget(self.onglets, 2)

        portions = meilleures_portions(self.trace, type_sortie)
        self._remplir(
            self.onglets, "🏅 Meilleures portions", portions,
            ["Portion", "Où (km)", "Temps", "Allure", "Vitesse", "D+", "FC moy."],
            lambda s: [s["libelle"], f"{s['debut_km']:.1f} → {s['fin_km']:.1f}".replace(".", ","),
                       formater_duree(s["duree_s"]), formater_allure(s["allure"]),
                       f"{s['vitesse_kmh']:.1f} km/h", f"{s['d_plus']} m",
                       f"{s['fc_moy']} bpm" if s["fc_moy"] else "—"],
            "Aucune portion calculable.")

        secteurs = secteurs_km(self.trace)
        self._remplir(
            self.onglets, "📏 Km par km", secteurs,
            ["Secteur", "Temps", "Allure", "Pente", "D+", "D−", "FC moy."],
            lambda s: [s["libelle"], formater_duree(s["duree_s"]), formater_allure(s["allure"]),
                       f"{s['pente_pct']:+.0f} %", f"{s['d_plus']} m", f"{s['d_moins']} m",
                       f"{s['fc_moy']} bpm" if s["fc_moy"] else "—"],
            "Aucun secteur.", marquer_extremes=True)

        terrain = repartition_terrain(self.trace)
        self._remplir_terrain(terrain)

    def _creer_table(self, colonnes):
        table = QTableWidget()
        table.setColumnCount(len(colonnes))
        table.setHorizontalHeaderLabels(colonnes)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        en_tete = table.horizontalHeader()
        en_tete.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        en_tete.setStretchLastSection(True)
        return table

    def _remplir(self, onglets, nom, lignes, colonnes, formateur, vide, marquer_extremes=False):
        table = self._creer_table(colonnes)
        table.setRowCount(len(lignes))
        allures = [s["allure"] for s in lignes if s.get("allure")]
        rapide = min(allures) if (marquer_extremes and len(allures) > 2) else None
        lent = max(allures) if (marquer_extremes and len(allures) > 2) else None
        for r, s in enumerate(lignes):
            for c, texte in enumerate(formateur(s)):
                item = QTableWidgetItem(texte)
                if rapide is not None and s.get("allure") == rapide:
                    item.setForeground(QColor("#66BB6A"))
                elif lent is not None and s.get("allure") == lent:
                    item.setForeground(QColor("#EF5350"))
                table.setItem(r, c, item)
        table.cellClicked.connect(lambda row, _c, l=lignes: self._surligner(l, row))
        if not lignes:
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem(vide))
        onglets.addTab(table, nom)

    def _surligner(self, lignes, row):
        if 0 <= row < len(lignes) and "x0" in lignes[row]:
            self.carte.surligner(lignes[row]["x0"], lignes[row]["x1"])

    def _remplir_terrain(self, terrain):
        table = self._creer_table(["Terrain", "Distance", "Temps", "Allure", "Vitesse"])
        table.setRowCount(max(len(terrain), 1))
        for r, s in enumerate(terrain):
            for c, texte in enumerate([
                s["libelle"], f"{s['distance_m'] / 1000:.1f} km".replace(".", ","),
                formater_duree(s["duree_s"]), formater_allure(s["allure"]),
                f"{s['vitesse_kmh']:.1f} km/h",
            ]):
                table.setItem(r, c, QTableWidgetItem(texte))
        if not terrain:
            table.setItem(0, 0, QTableWidgetItem("Pas assez de données."))
        self.onglets.addTab(table, "⛰️ Terrain")


def ouvrir_meilleures_portions(parent, points, titre_sortie="", type_sortie=""):
    dialogue = DialogueMeilleuresPortions(points, titre_sortie, type_sortie, parent)
    dialogue.exec()
