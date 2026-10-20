"""
Journal (style D5, sombre) : le fil de ta vie d'athlète, jour après jour —
sorties avec ressenti, notes et photos, pesées, blessures, courses. Un clic
sur une sortie ouvre sa fiche.
"""

import os
from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QButtonGroup,
)

import data.metriques as met
from data import photos_sorties
from data.database import connexion
from interface.forme_evolution import _EcranAthlete
from interface.detail_sortie import style_sombre

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
ICONES_TYPE = {"Trail": "⛰️", "Course": "🏃", "VTT": "🚵", "Vélo": "🚴", "Randonnée": "🥾", "Route": "🛣️"}
FILTRES = [("Tout", None), ("Sorties", "sortie"), ("Santé", "sante"), ("Photos", "photo")]
A_TEXTE, A_SEC, A_DISCRET, A_CARTE, A_BORDURE, A_FOND = "#F3F6F7", "#9AA7AE", "#6B767D", "#1B2126", "#262E34", "#12151A"


class CarteEntree(QFrame):
    clique = Signal()

    def __init__(self, cliquable=False):
        super().__init__()
        self.setObjectName("entreeJournal")
        self.setStyleSheet(f"#entreeJournal {{ background:{A_CARTE}; border:1px solid {A_BORDURE}; border-radius:14px; }}"
                           f"#entreeJournal:hover {{ border-color:{'#2E7D32' if cliquable else A_BORDURE}; }}"
                           f"QLabel {{ background:transparent; color:{A_TEXTE}; }}")
        self._cliquable = cliquable
        if cliquable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 12, 16, 12)
        self.lay.setSpacing(4)

    def mouseReleaseEvent(self, e):
        if self._cliquable and e.button() == Qt.MouseButton.LeftButton:
            self.clique.emit()
        super().mouseReleaseEvent(e)


def _l(texte, style="", sec=False):
    l = QLabel(texte)
    l.setWordWrap(True)
    l.setStyleSheet(f"color:{A_SEC if sec else A_TEXTE};{style}")
    l.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    return l


def entrees_journal(athlete_id, depuis, jusqu_a=None):
    """Liste d'entrées {jour, genre, ...} triées du plus récent au plus ancien."""
    jusqu_a = jusqu_a or date.today()
    res = []
    for s in met.activites_periode(athlete_id, depuis, jusqu_a):
        if not s["jour"]:
            continue
        from interface.ressenti import texte_ressenti
        res.append({"jour": s["jour"], "genre": "sortie", "s": s,
                    "ressenti": texte_ressenti(met.ressenti_de_sortie(s["id"])),
                    "photos": photos_sorties.photos_de_sortie(s["id"])[:4]})
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT date, poids_kg, etat_jambes, notes FROM suivi_corporel WHERE athlete_id=? AND date>=? AND date<=?",
                (athlete_id, depuis.isoformat(), jusqu_a.isoformat() + "z"))
    for d, poids, jambes, notes in cur.fetchall():
        j = met._jour(d)
        if j:
            res.append({"jour": j, "genre": "sante", "poids": poids, "jambes": jambes, "notes": notes})
    cur.execute("SELECT date_debut, date_fin, zone_corporelle, type_blessure, statut FROM blessures WHERE athlete_id=?", (athlete_id,))
    for dd, df, zone, typ, st in cur.fetchall():
        j = met._jour(dd)
        if j and depuis <= j <= jusqu_a:
            res.append({"jour": j, "genre": "sante", "blessure": f"Blessure : {zone or ''}{' — ' + typ if typ else ''}", "statut": st})
        jf = met._jour(df) if df else None
        if jf and depuis <= jf <= jusqu_a:
            res.append({"jour": jf, "genre": "sante", "blessure": f"Fin de blessure : {zone or ''}", "statut": "Guérie"})
    conn.close()
    res.sort(key=lambda e: e["jour"], reverse=True)
    return res


class Journal(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📓  Journal", "Le fil de tes entraînements, jour après jour.", athlete_id_initial)
        self.nb_jours = 60
        self.filtre = None
        puces = QHBoxLayout()
        self.groupe = QButtonGroup(self)
        for lib, cle in FILTRES:
            b = QPushButton(lib)
            b.setCheckable(True)
            b.setChecked(cle is None)
            b.setStyleSheet(f"QPushButton {{ background:{A_CARTE}; color:{A_SEC}; border:1px solid {A_BORDURE}; border-radius:14px; padding:5px 14px; }}"
                            "QPushButton:checked { background:#2E7D32; color:white; border-color:#2E7D32; }")
            b.clicked.connect(lambda _=False, c=cle: self._filtrer(c))
            self.groupe.addButton(b)
            puces.addWidget(b)
        puces.addStretch(1)
        self.principal.addLayout(puces)
        self.fil = QVBoxLayout()
        self.fil.setSpacing(8)
        self.principal.addLayout(self.fil)
        self.plus = QPushButton("Voir plus ancien…")
        self.plus.setObjectName("boutonSecondaire")
        self.plus.clicked.connect(self._plus)
        self.principal.addWidget(self.plus, 0, Qt.AlignmentFlag.AlignHCenter)
        self.principal.addStretch(1)
        self._finaliser()
        self.setStyleSheet(style_sombre() + f"QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget {{ background:{A_FOND}; }}")

    def _filtrer(self, cle):
        self.filtre = cle
        self.actualiser()

    def _plus(self):
        self.nb_jours += 90
        self.actualiser()

    def _vider(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._vider(it.layout())

    def actualiser(self):
        self._vider(self.fil)
        a = self.athlete_id
        if a is None:
            self.fil.addWidget(_l("Sélectionne un athlète.", sec=True))
            return
        entrees = entrees_journal(a, date.today() - timedelta(days=self.nb_jours))
        if self.filtre == "photo":
            entrees = [e for e in entrees if e["genre"] == "sortie" and e["photos"]]
        elif self.filtre:
            entrees = [e for e in entrees if e["genre"] == self.filtre]
        if not entrees:
            self.fil.addWidget(_l("Rien à afficher sur cette période.", sec=True))
        mois_cour, jour_cour = None, None
        for e in entrees:
            j = e["jour"]
            if (j.year, j.month) != mois_cour:
                mois_cour = (j.year, j.month)
                self.fil.addSpacing(10)
                self.fil.addWidget(_l(f"{MOIS[j.month - 1].upper()} {j.year}", f"font-size:13px; font-weight:800; color:{A_DISCRET};"))
            if j != jour_cour:
                jour_cour = j
                aujourd = " · aujourd'hui" if j == date.today() else ""
                self.fil.addWidget(_l(f"{JOURS[j.weekday()]} {j.day}{aujourd}", f"font-size:15px; font-weight:700; color:#66BB6A;"))
            self.fil.addWidget(self._carte(e))
        self.plus.setText(f"Voir plus ancien… (actuellement {self.nb_jours} jours)")

    def _carte(self, e):
        if e["genre"] == "sortie":
            s = e["s"]
            c = CarteEntree(True)
            c.clique.connect(lambda i=s["id"]: self._ouvrir(i))
            mn = s["duree"] // 60
            c.lay.addWidget(_l(f"{ICONES_TYPE.get(s['type'], '🏅')}  {s['nom'] or s['type'] or 'Sortie'}", "font-size:16px; font-weight:700;"))
            c.lay.addWidget(_l(f"{s['distance']:.1f} km · {s['denivele']} m D+ · {mn // 60} h {mn % 60:02d}" +
                               (f" · FC {s['fc_moy']}" if s["fc_moy"] else ""), "font-size:13px;", True))
            if e["ressenti"]:
                c.lay.addWidget(_l(e["ressenti"], "font-size:12px;", True))
            if e["photos"]:
                ligne = QHBoxLayout()
                for p in e["photos"]:
                    chemin = photos_sorties.chemin_photo(p.get("fichier") or "")
                    pm = QPixmap(str(chemin)) if chemin and os.path.exists(str(chemin)) else QPixmap()
                    if not pm.isNull():
                        mini = QLabel()
                        mini.setPixmap(pm.scaled(110, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation).copy(0, 0, 110, 80))
                        mini.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                        ligne.addWidget(mini)
                ligne.addStretch(1)
                c.lay.addLayout(ligne)
            return c
        c = CarteEntree(False)
        if e.get("blessure"):
            c.lay.addWidget(_l("🩹  " + e["blessure"], "font-size:14px; font-weight:600;"))
        else:
            morceaux = []
            if e.get("poids"):
                morceaux.append(f"⚖️ {e['poids']:.1f} kg".replace(".", ","))
            if e.get("jambes"):
                morceaux.append(f"Jambes : {e['jambes']}")
            c.lay.addWidget(_l("  ·  ".join(morceaux) or "Suivi du corps", "font-size:14px; font-weight:600;"))
            if e.get("notes"):
                c.lay.addWidget(_l(e["notes"], "font-size:12px;", True))
        return c

    def _ouvrir(self, activite_id):
        from interface.detail_sortie import DialogueDetailSortie
        DialogueDetailSortie(activite_id, self.athlete_id, parent=self, au_enregistrement=self.actualiser).exec()
