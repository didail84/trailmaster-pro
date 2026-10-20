"""
Blocs « Aperçu » du tableau de bord : la forme du moment en six cartes,
la courbe forme / fatigue sur 6 mois, et les dernières sorties.

Chaque bloc se met à jour seul via actualiser(athlete_id) ; le tableau de
bord les appelle à chaque rafraîchissement.
"""

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QStyle, QStyledItemDelegate, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton,
)

from data.database import connexion
from interface.coach import calculer_serie_forme
from interface.courbe_multiligne import CourbeMultiLignes
from interface.theme import PALETTE
from interface.vo2max import estimer_vo2max, estimer_vo2max_recent

COULEURS_TYPE = {
    "Trail": "#F9A825", "Course": "#42A5F5", "Randonnée": "#66BB6A",
    "VTT": "#AB47BC", "Vélo": "#26A69A", "Musculation": "#EF5350",
}
COULEUR_TYPE_AUTRE = "#8A949B"

VERT, ORANGE, ROUGE = "#66BB6A", "#F9A825", "#EF5350"


# ------------------------------------------------------------------
# Petits utilitaires partagés avec d'autres écrans
# ------------------------------------------------------------------

def creer_pastille_type(type_sortie):
    """Pastille arrondie colorée selon le type de sortie (Trail, Course…)."""
    texte = type_sortie or "—"
    couleur = COULEURS_TYPE.get(type_sortie, COULEUR_TYPE_AUTRE)
    etiquette = QLabel(texte)
    etiquette.setAlignment(Qt.AlignmentFlag.AlignCenter)
    etiquette.setStyleSheet(
        f"QLabel {{ color: {couleur}; border: 1px solid {couleur}; border-radius: 10px;"
        f" padding: 1px 10px; font-size: 11.5px; font-weight: 600; background: transparent; }}"
    )
    conteneur = QFrame()
    conteneur.setStyleSheet("background: transparent; border: none;")
    lay = QHBoxLayout(conteneur)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.addWidget(etiquette)
    lay.addStretch()
    return conteneur


class DelegatePastilleType(QStyledItemDelegate):
    """Dessine le type de sortie en pastille colorée dans une colonne de
    tableau — sans widget par cellule, donc compatible avec le tri."""

    def paint(self, painter, option, index):
        texte = str(index.data() or "")
        couleur = COULEURS_TYPE.get(texte)
        if not couleur:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        police = option.font
        painter.setFont(police)
        fm = option.fontMetrics
        largeur = fm.horizontalAdvance(texte) + 22
        hauteur = fm.height() + 4
        rect = QRectF(option.rect.left() + 6, option.rect.center().y() - hauteur / 2, largeur, hauteur)
        painter.setPen(QPen(QColor(couleur), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, hauteur / 2, hauteur / 2)
        painter.setPen(QColor(couleur))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texte)
        painter.restore()

    def sizeHint(self, option, index):
        taille = super().sizeHint(option, index)
        taille.setWidth(taille.width() + 30)
        return taille


def date_fr(date_iso):
    """'2026-10-11 08:00:00' -> '11/10/2026'."""
    texte = str(date_iso or "")[:10]
    try:
        return datetime.strptime(texte, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return texte or "—"


def virgule(valeur, decimales=1):
    return f"{valeur:.{decimales}f}".replace(".", ",")


def duree_hmm(secondes):
    if not secondes:
        return "—"
    total = int(secondes // 60)
    return f"{total // 60}h{total % 60:02d}"


def etat_fraicheur(valeur):
    """Libellé et couleur de la fraîcheur (forme moins fatigue)."""
    if valeur > 5:
        return "Frais", VERT
    if valeur > -10:
        return "Équilibré", VERT
    if valeur > -25:
        return "Chargé", ORANGE
    return "Très fatigué", ROUGE


def _carte_mesure(titre):
    carte = QFrame()
    carte.setObjectName("carte")
    carte.setMinimumHeight(118)
    lay = QVBoxLayout(carte)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(4)
    t = QLabel(titre.upper())
    t.setObjectName("titreCarte")
    v = QLabel("—")
    v.setObjectName("valeurCarte")
    d = QLabel("")
    d.setObjectName("texteSecondaire")
    d.setWordWrap(True)
    d.setTextFormat(Qt.TextFormat.RichText)
    lay.addWidget(t)
    lay.addWidget(v)
    lay.addWidget(d)
    lay.addStretch()
    carte.valeur = v
    carte.detail = d
    return carte


# ------------------------------------------------------------------
# 1. Forme du moment : six cartes
# ------------------------------------------------------------------

class ApercuCartes(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("apercuCartes")
        self.setStyleSheet("#apercuCartes { background: transparent; border: none; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        titre = QLabel("Forme du moment")
        titre.setStyleSheet(
            f"color: {PALETTE['texte']}; font-size: 20px; font-weight: 700; background: transparent;")
        note = QLabel(
            "Modèle simplifié : charge de chaque jour = minutes + D+/10, lissée sur 42 jours "
            "(forme) et 7 jours (fatigue)."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        lay.addWidget(titre)
        lay.addWidget(note)

        grille = QGridLayout()
        grille.setHorizontalSpacing(12)
        grille.setVerticalSpacing(12)
        self.cartes = {}
        for i, (cle, nom) in enumerate([
            ("forme", "Forme (fitness)"), ("fatigue", "Fatigue"), ("fraicheur", "Fraîcheur"),
            ("vo2_recent", "VO2max récent"), ("vo2_record", "VO2max record"),
            ("poids", "Dernier poids"),
        ]):
            carte = _carte_mesure(nom)
            self.cartes[cle] = carte
            grille.addWidget(carte, i // 3, i % 3)
        for c in range(3):
            grille.setColumnStretch(c, 1)
        lay.addLayout(grille)

    def actualiser(self, athlete_id):
        c = self.cartes
        for carte in c.values():
            carte.valeur.setText("—")
            carte.valeur.setStyleSheet("")
            carte.detail.setText("")
        if athlete_id is None:
            return

        serie = calculer_serie_forme(athlete_id, nb_jours=180)
        if serie:
            dernier = serie[-1]
            c["forme"].valeur.setText(virgule(dernier["fitness"]))
            c["forme"].detail.setText("moyenne 42 jours")
            c["fatigue"].valeur.setText(virgule(dernier["fatigue"]))
            c["fatigue"].detail.setText("moyenne 7 jours")
            fraicheur = dernier["forme"]
            etat, couleur = etat_fraicheur(fraicheur)
            c["fraicheur"].valeur.setText(f"{'+' if fraicheur > 0 else ''}{virgule(fraicheur)}".replace("-", "−"))
            c["fraicheur"].detail.setText(f'<span style="color:{couleur}">● {etat}</span>')

        recent = estimer_vo2max_recent(athlete_id, 180)
        if recent:
            c["vo2_recent"].valeur.setText(virgule(recent["vo2max"]))
            c["vo2_recent"].detail.setText(f"meilleur effort des 180 j · {date_fr(recent['date'])}")
        else:
            c["vo2_recent"].detail.setText("pas d'effort Trail/Course récent de 3 km ou plus")

        record = self._record_vo2max(athlete_id)
        if record:
            c["vo2_record"].valeur.setText(virgule(record[0]))
            c["vo2_record"].detail.setText(
                f"record du {date_fr(record[1])} (à ne pas prendre pour la forme actuelle)")

        poids = self._dernier_poids(athlete_id)
        if poids:
            c["poids"].valeur.setText(f"{virgule(poids[0])} kg")
            c["poids"].detail.setText(f"relevé du {date_fr(poids[1])}")

    @staticmethod
    def _record_vo2max(athlete_id):
        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "SELECT date, distance, duree, vo2max FROM activites WHERE athlete_id=? "
            "AND type IN ('Trail','Course') AND distance >= 3 AND duree > 0",
            (athlete_id,),
        )
        lignes = cur.fetchall()
        conn.close()
        meilleur = None
        for d, dist, duree, vo2 in lignes:
            if duree / dist < 230:      # plus rapide que 3:50/km : donnée aberrante
                continue
            valeur = vo2 if vo2 else estimer_vo2max(dist, duree)
            if valeur and (meilleur is None or valeur > meilleur[0]):
                meilleur = (valeur, d)
        return meilleur

    @staticmethod
    def _dernier_poids(athlete_id):
        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "SELECT poids_kg, date FROM suivi_corporel WHERE athlete_id=? AND poids_kg IS NOT NULL "
            "AND poids_kg > 0 ORDER BY date DESC, id DESC LIMIT 1", (athlete_id,))
        ligne = cur.fetchone()
        conn.close()
        return ligne


# ------------------------------------------------------------------
# 2. Courbe forme / fatigue sur 6 mois
# ------------------------------------------------------------------

class ApercuCourbe(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("carteGrande")
        lay = QVBoxLayout(self)
        titre = QLabel("Forme et fatigue sur 6 mois")
        titre.setObjectName("titreCarte")
        note = QLabel("Passe la souris sur la courbe pour lire les valeurs.")
        note.setObjectName("texteSecondaire")
        self.courbe = CourbeMultiLignes()
        self.courbe.setMinimumHeight(260)
        lay.addWidget(titre)
        lay.addWidget(note)
        lay.addWidget(self.courbe)

    def actualiser(self, athlete_id):
        if athlete_id is None:
            self.courbe.definir_series([])
            return
        serie = calculer_serie_forme(athlete_id, nb_jours=180)
        self.courbe.definir_series([
            {"nom": "Forme", "couleur": "#42A5F5",
             "valeurs": [(j["date"].strftime("%d/%m"), j["fitness"]) for j in serie]},
            {"nom": "Fatigue", "couleur": "#FFA726",
             "valeurs": [(j["date"].strftime("%d/%m"), j["fatigue"]) for j in serie]},
        ])


# ------------------------------------------------------------------
# 3. Dernières sorties
# ------------------------------------------------------------------

STYLE_TABLE = """
    QHeaderView {{ background-color: transparent; border: none; }}
    QTableCornerButton::section {{ background-color: transparent; border: none; }}
    QTableWidget {{
        background-color: transparent; border: none; gridline-color: {bordure};
        color: {texte}; selection-background-color: {accent};
    }}
    QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {bordure}; }}
    QHeaderView::section {{
        background-color: transparent; color: {discret}; padding: 8px; border: none;
        border-bottom: 1px solid {bordure}; font-weight: 600; font-size: 11px;
    }}
"""


def style_table_sobre():
    from interface.theme import obtenir_couleur_accent_douce
    return STYLE_TABLE.format(
        bordure=PALETTE.get("bordure_douce", "#262D33"), texte=PALETTE["texte"],
        discret=PALETTE.get("texte_discret", "#8A949B"),
        accent=obtenir_couleur_accent_douce(0.25),
    )


class DernieresSorties(QFrame):

    def __init__(self, ouvrir_fiche=None, ouvrir_historique=None, nombre=10, parent=None):
        super().__init__(parent)
        self.setObjectName("carteGrande")
        self._ouvrir_fiche = ouvrir_fiche
        self._ids = []
        self._nombre = nombre
        lay = QVBoxLayout(self)
        entete = QHBoxLayout()
        titre = QLabel("Dernières sorties")
        titre.setObjectName("titreCarte")
        entete.addWidget(titre)
        entete.addStretch()
        if ouvrir_historique:
            bouton = QPushButton("Voir tout l'historique →")
            bouton.setStyleSheet(
                f"QPushButton {{ background-color: {PALETTE['carte_haute']}; color: {PALETTE['texte_att']};"
                f" border: 1px solid {PALETTE['bordure']}; border-radius: 8px; padding: 6px 12px; }}"
                f"QPushButton:hover {{ color: {PALETTE['texte']}; }}")
            bouton.setCursor(Qt.CursorShape.PointingHandCursor)
            bouton.clicked.connect(ouvrir_historique)
            entete.addWidget(bouton)
        lay.addLayout(entete)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["DATE", "SORTIE", "TYPE", "KM", "D+", "DURÉE", "FC"])
        self.table.setStyleSheet(style_table_sobre())
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setCursor(Qt.CursorShape.PointingHandCursor)
        en_tete = self.table.horizontalHeader()
        en_tete.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        en_tete.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        en_tete.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 130)
        en_tete.setStretchLastSection(False)
        self.table.cellClicked.connect(self._clic)
        lay.addWidget(self.table)

    def _clic(self, ligne, _col):
        if self._ouvrir_fiche and 0 <= ligne < len(self._ids):
            self._ouvrir_fiche(self._ids[ligne])

    def actualiser(self, athlete_id):
        self.table.setRowCount(0)
        self._ids = []
        if athlete_id is None:
            return
        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne "
            "FROM activites WHERE athlete_id=? ORDER BY date DESC LIMIT ?",
            (athlete_id, self._nombre),
        )
        lignes = cur.fetchall()
        conn.close()
        self.table.setRowCount(len(lignes))
        for r, (id_, d, nom, type_, km, dp, duree, fc) in enumerate(lignes):
            self._ids.append(id_)
            valeurs = [date_fr(d), nom or "—", None,
                       virgule(km or 0), f"{round(dp or 0)}", duree_hmm(duree),
                       f"{round(fc)}" if fc else "—"]
            for c, v in enumerate(valeurs):
                if v is None:
                    self.table.setCellWidget(r, c, creer_pastille_type(type_))
                else:
                    item = QTableWidgetItem(v)
                    if c in (3, 4, 5, 6):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(r, c, item)
            self.table.setRowHeight(r, 38)
        self.table.setFixedHeight(40 + 38 * len(lignes) + 4)
