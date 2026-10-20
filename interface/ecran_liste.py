"""
Écran générique de type "fiche" : sélecteur d'athlète, formulaire
d'ajout et tableau listant les entrées existantes, avec suppression.

Utilisé par tous les nouveaux modules simples de TrailMaster Pro
(Sommeil, Blessures, Matériel, Résultats de courses, Zones
d'entraînement, Nutrition, Objectifs) pour éviter de dupliquer 7 fois
la même mécanique de formulaire + tableau + CRUD.
"""

from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QMessageBox,
    QScrollArea,
)

from data.database import connexion, creer_base_de_donnees, obtenir_athletes


def configurer_table_redimensionnable(table):
    """Rend une QTableWidget confortable à consulter quel que soit le
    nombre de colonnes ou la longueur du contenu : colonnes ET lignes
    redimensionnables à la main (glisser leur bord), avec défilement
    horizontal ET vertical dès que le contenu dépasse la fenêtre —
    plutôt que des colonnes comprimées de force pour tenir dedans.

    À appeler une fois juste après la création de chaque QTableWidget
    de l'application (avant ou après remplissage, peu importe) — y
    compris dans les futurs écrans, pour un comportement cohérent
    partout sans avoir à le répéter à la main à chaque fois."""

    en_tete_horizontal = table.horizontalHeader()
    en_tete_horizontal.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    en_tete_horizontal.setMinimumSectionSize(70)
    en_tete_horizontal.setStretchLastSection(False)

    en_tete_vertical = table.verticalHeader()
    en_tete_vertical.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    en_tete_vertical.setDefaultSectionSize(32)
    en_tete_vertical.setMinimumSectionSize(20)

    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


@dataclass
class Champ:
    """Décrit un champ du formulaire ET une colonne SQL du même nom."""

    nom: str
    label: str
    type: str = "texte"  # texte | texte_long | entier | decimal | date | choix
    choix: list = field(default_factory=list)
    obligatoire: bool = False


class EcranListe(QMainWindow):

    def __init__(
        self,
        titre,
        sous_titre,
        icone,
        table_sql,
        champs,
        athlete_id_initial=None,
        tri="id DESC",
        colonnes_calculees=None,
        bouton_extra=None,
    ):
        super().__init__()

        # colonnes_calculees : liste optionnelle de {"label": str,
        # "fonction": callable(id_ligne, valeurs) -> str} ajoutées en
        # lecture seule après les colonnes normales (ex. un kilométrage
        # recalculé depuis les vraies activités plutôt que ressaisi à
        # la main).
        self.colonnes_calculees = colonnes_calculees or []

        # bouton_extra : tuple optionnel (label, callback(self)), ou
        # liste de tels tuples, pour une ou plusieurs actions
        # supplémentaires sous le tableau (ex. "Lier une activité"),
        # sans devoir dupliquer tout l'écran pour ça.
        if bouton_extra and isinstance(bouton_extra, tuple):
            bouton_extra = [bouton_extra]
        self.boutons_extra = bouton_extra or []

        self.table_sql = table_sql
        self.champs = champs
        self.tri = tri
        self.lignes_ids = []

        creer_base_de_donnees()

        self.setWindowTitle(f"TrailMaster Pro – {titre}")
        self.resize(1200, 780)
        self.setMinimumSize(950, 650)

        central = QWidget()
        conteneur_scroll = QScrollArea()
        conteneur_scroll.setWidgetResizable(True)
        conteneur_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        conteneur_scroll.setFrameShape(QFrame.Shape.NoFrame)
        conteneur_scroll.setWidget(central)
        self.setCentralWidget(conteneur_scroll)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(15)

        bouton_retour = QPushButton("← Aujourd'hui")
        bouton_retour.setObjectName("boutonRetourTableauBord")
        bouton_retour.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_retour.clicked.connect(self.close)
        principal.addWidget(bouton_retour, 0, Qt.AlignmentFlag.AlignLeft)

        titre_label = QLabel(f"{icone}  {titre}")
        titre_label.setObjectName("titrePage")

        sous_titre_label = QLabel(sous_titre)
        sous_titre_label.setObjectName("sousTitrePage")

        principal.addWidget(titre_label)
        principal.addWidget(sous_titre_label)

        # ------------------------------------------------------------
        # SÉLECTEUR ATHLÈTE
        # ------------------------------------------------------------

        barre_athlete = QHBoxLayout()
        label_athlete = QLabel("Athlète :")
        label_athlete.setObjectName("labelChamp")

        self.combo_athlete = QComboBox()
        self.athletes = obtenir_athletes()
        self.combo_athlete.addItem("Tous les athlètes", None)
        for a in self.athletes:
            self.combo_athlete.addItem(f"{a[2]} {a[1]}", a[0])

        barre_athlete.addWidget(label_athlete)
        barre_athlete.addWidget(self.combo_athlete)
        barre_athlete.addStretch()
        principal.addLayout(barre_athlete)

        # Emplacement libre, sous le sélecteur d'athlète, pour qu'un écran
        # dérivé y ajoute ses propres blocs (cartes de résumé, courbes…).
        self.zone_haut = QVBoxLayout()
        self.zone_haut.setSpacing(15)
        principal.addLayout(self.zone_haut)

        # ------------------------------------------------------------
        # FORMULAIRE D'AJOUT
        # ------------------------------------------------------------

        cadre_form = QFrame()
        cadre_form.setObjectName("carteForm")
        form_wrap = QVBoxLayout(cadre_form)

        form_titre = QLabel("Ajouter une entrée")
        form_titre.setObjectName("titreCarte")
        form_wrap.addWidget(form_titre)

        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(10)
        self.widgets_champs = {}

        for champ in self.champs:
            widget = self._creer_widget_champ(champ)
            self.widgets_champs[champ.nom] = widget
            label = QLabel(champ.label + (" *" if champ.obligatoire else ""))
            label.setObjectName("labelChamp")
            self.form_layout.addRow(label, widget)

        form_wrap.addLayout(self.form_layout)

        bouton_ajouter = QPushButton("+ Ajouter")
        bouton_ajouter.setObjectName("boutonPrincipal")
        bouton_ajouter.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_ajouter.clicked.connect(self.ajouter_ligne)
        form_wrap.addWidget(bouton_ajouter)

        self.cadre_form = cadre_form
        self.principal = principal
        principal.addWidget(cadre_form)

        # ------------------------------------------------------------
        # TABLEAU
        # ------------------------------------------------------------

        self.table = QTableWidget()
        colonnes = [c.label for c in self.champs] + [c["label"] for c in self.colonnes_calculees]
        self.table.setColumnCount(len(colonnes))
        self.table.setHorizontalHeaderLabels(colonnes)
        configurer_table_redimensionnable(self.table)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Sans hauteur minimale, le tableau n'a par défaut presque pas
        # de minimumSizeHint (juste l'en-tête) : dès que le formulaire
        # d'ajout (surtout avec beaucoup de champs, ex. Courses à venir,
        # Alimentation...) prend déjà presque toute la hauteur de la
        # fenêtre, le tableau se retrouve écrasé à quelques pixels — on
        # ne voit quasiment aucune ligne, et la barre de défilement
        # verticale de la fenêtre (qui existe bien, mais ne révèle
        # presque rien dans ce cas) passe facilement inaperçue à côté
        # de la barre horizontale, bien visible elle à cause du nombre
        # de colonnes. Une hauteur minimale garantit toujours quelques
        # lignes visibles, et donc une vraie barre verticale exploitable
        # pour dérouler le reste de l'écran.
        self.table.setMinimumHeight(260)
        principal.addWidget(self.table, 1)

        barre_boutons_bas = QHBoxLayout()

        bouton_supprimer = QPushButton("Supprimer la ligne sélectionnée")
        bouton_supprimer.setObjectName("boutonSecondaire")
        bouton_supprimer.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton_supprimer.clicked.connect(self.supprimer_ligne)
        barre_boutons_bas.addWidget(bouton_supprimer)

        for label_extra, callback_extra in self.boutons_extra:
            bouton_action_extra = QPushButton(label_extra)
            bouton_action_extra.setObjectName("boutonPrincipal")
            bouton_action_extra.setCursor(Qt.CursorShape.PointingHandCursor)
            bouton_action_extra.clicked.connect(
                lambda checked=False, cb=callback_extra: cb(self)
            )
            barre_boutons_bas.addWidget(bouton_action_extra)

        barre_boutons_bas.addStretch()
        principal.addLayout(barre_boutons_bas)

        self.setStyleSheet(obtenir_style_ecran())

        # La présélection de l'athlète actif et la connexion du signal se
        # font seulement maintenant, une fois self.table déjà construit :
        # sinon setCurrentIndex() déclenche charger_donnees() prématurément
        # (avant que le tableau n'existe) et fait planter l'écran.
        if athlete_id_initial is not None:
            for i in range(self.combo_athlete.count()):
                if self.combo_athlete.itemData(i) == athlete_id_initial:
                    self.combo_athlete.setCurrentIndex(i)
                    break

        self.combo_athlete.currentIndexChanged.connect(self.charger_donnees)

        self.charger_donnees()

    # ------------------------------------------------------------
    # CONSTRUCTION DES WIDGETS DE FORMULAIRE
    # ------------------------------------------------------------

    def _creer_widget_champ(self, champ):
        if champ.type == "entier":
            w = QSpinBox()
            w.setRange(-100000, 100000)
            return w
        if champ.type == "decimal":
            w = QDoubleSpinBox()
            w.setRange(-100000, 100000)
            w.setDecimals(2)
            return w
        if champ.type == "date":
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDate(QDate.currentDate())
            return w
        if champ.type == "choix":
            w = QComboBox()
            w.addItems(champ.choix)
            return w
        if champ.type == "texte_long":
            w = QTextEdit()
            w.setFixedHeight(60)
            return w
        return QLineEdit()

    def _valeur_widget(self, champ):
        w = self.widgets_champs[champ.nom]
        if champ.type in ("entier", "decimal"):
            return w.value()
        if champ.type == "date":
            return w.date().toString("yyyy-MM-dd")
        if champ.type == "choix":
            return w.currentText()
        if champ.type == "texte_long":
            return w.toPlainText().strip()
        return w.text().strip()

    def _vider_widget(self, champ):
        w = self.widgets_champs[champ.nom]
        if champ.type in ("entier", "decimal"):
            w.setValue(0)
        elif champ.type == "date":
            w.setDate(QDate.currentDate())
        elif champ.type == "choix":
            w.setCurrentIndex(0)
        elif champ.type == "texte_long":
            w.clear()
        else:
            w.clear()

    # ------------------------------------------------------------
    # DONNÉES
    # ------------------------------------------------------------

    def athlete_selectionne_id(self):
        return self.combo_athlete.currentData()

    def charger_donnees(self):
        conn = connexion()
        cur = conn.cursor()

        colonnes_sql = ", ".join(c.nom for c in self.champs)
        athlete_id = self.athlete_selectionne_id()

        if athlete_id is None:
            cur.execute(
                f"SELECT id, {colonnes_sql} FROM {self.table_sql} ORDER BY {self.tri}"
            )
        else:
            cur.execute(
                f"SELECT id, {colonnes_sql} FROM {self.table_sql} "
                f"WHERE athlete_id=? ORDER BY {self.tri}",
                (athlete_id,),
            )

        lignes = cur.fetchall()
        conn.close()

        self.lignes_ids = [l[0] for l in lignes]
        self.table.setRowCount(len(lignes))
        nb_champs = len(self.champs)
        for i, ligne in enumerate(lignes):
            for j, valeur in enumerate(ligne[1:]):
                item = QTableWidgetItem("" if valeur is None else str(valeur))
                self.table.setItem(i, j, item)

            for k, colonne_calc in enumerate(self.colonnes_calculees):
                try:
                    valeur_calculee = colonne_calc["fonction"](ligne[0], ligne[1:])
                except Exception:
                    valeur_calculee = "—"
                self.table.setItem(i, nb_champs + k, QTableWidgetItem(str(valeur_calculee)))

        self.table.resizeColumnsToContents()

    def ajouter_ligne(self):
        if len(self.athletes) == 0:
            QMessageBox.warning(
                self, "Aucun athlète",
                "Créez d'abord un athlète dans l'écran Athlètes."
            )
            return

        athlete_id = self.athlete_selectionne_id()
        if athlete_id is None:
            QMessageBox.warning(
                self, "Athlète requis",
                "Sélectionnez un athlète précis (pas « Tous ») avant d'ajouter une entrée."
            )
            return

        valeurs = []
        for champ in self.champs:
            v = self._valeur_widget(champ)
            if champ.obligatoire and (v == "" or v is None):
                QMessageBox.warning(
                    self, "Champ requis",
                    f"Le champ « {champ.label} » est obligatoire."
                )
                return
            valeurs.append(v)

        colonnes_sql = ", ".join(c.nom for c in self.champs)
        points_interrogation = ", ".join(["?"] * len(self.champs))

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {self.table_sql} (athlete_id, {colonnes_sql}) "
            f"VALUES (?, {points_interrogation})",
            (athlete_id, *valeurs),
        )
        conn.commit()
        conn.close()

        for champ in self.champs:
            self._vider_widget(champ)

        self.charger_donnees()

    def supprimer_ligne(self):
        ligne = self.table.currentRow()
        if ligne < 0:
            QMessageBox.information(
                self, "Sélection requise",
                "Sélectionnez d'abord une ligne à supprimer."
            )
            return

        id_ligne = self.lignes_ids[ligne]
        confirmation = QMessageBox.question(
            self, "Confirmer la suppression",
            "Supprimer définitivement cette entrée ?",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        conn = connexion()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {self.table_sql} WHERE id=?", (id_ligne,))
        conn.commit()
        conn.close()

        self.charger_donnees()


# ==================================================================
# STYLE COMMUN — charte graphique de tout le logiciel (fond sombre,
# cartes arrondies, typographie Sora / IBM Plex Sans, accent
# personnalisable). Toute future modification visuelle globale se
# fait ici : ce gabarit est partagé par tous les écrans qui appellent
# obtenir_style_ecran(), qu'ils utilisent ou non EcranListe.
# ==================================================================

_STYLE_ECRAN_MODELE = """
    #boutonRetourTableauBord {
        background-color: transparent;
        color: PALETTE_TEXTE_SECONDAIRE;
        border: none;
        font-family: 'POLICE_TEXTE', sans-serif;
        font-size: 12.5px;
        padding: 2px 0px 8px 0px;
        text-align: left;
    }

    #boutonRetourTableauBord:hover {
        color: ACCENT_COLOR;
    }

    QScrollBar:vertical, QScrollBar:horizontal {
        background-color: transparent;
        width: 10px;
        height: 10px;
        margin: 0px;
    }

    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
        background-color: #2A3238;
        border-radius: 5px;
        min-height: 30px;
        min-width: 30px;
    }

    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
        background-color: #384048;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        height: 0px;
        width: 0px;
    }

    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
    }

    QMainWindow {
        background-color: PALETTE_FOND;
    }

    QWidget {
        background-color: PALETTE_FOND;
        color: PALETTE_TEXTE;
        font-family: 'POLICE_TEXTE', 'Segoe UI', sans-serif;
        font-size: 13px;
    }

    #titrePage {
        color: PALETTE_TEXTE;
        font-family: 'POLICE_TITRE', 'Segoe UI', sans-serif;
        font-size: 25px;
        font-weight: bold;
    }

    #sousTitrePage {
        color: PALETTE_TEXTE_SECONDAIRE;
        font-size: 13.5px;
    }

    #labelChamp {
        color: PALETTE_TEXTE_SECONDAIRE;
        font-size: 12.5px;
        font-weight: 500;
    }

    #carteForm {
        background-color: PALETTE_CARTE;
        border: 1px solid PALETTE_BORDURE;
        border-radius: 14px;
        padding: 12px;
    }

    #carteForm QLabel {
        background: transparent;
    }

    #titreCarte {
        color: PALETTE_TEXTE_DISCRET;
        font-size: 12px;
        font-weight: bold;
    }

    #texteSecondaire {
        color: PALETTE_TEXTE_SECONDAIRE;
        font-size: 13px;
    }

    QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QTextEdit {
        background-color: PALETTE_CARTE_HAUTE;
        color: PALETTE_TEXTE;
        border: 1px solid PALETTE_BORDURE;
        border-radius: 8px;
        padding: 7px 9px;
        selection-background-color: ACCENT_COLOR;
    }

    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus,
    QComboBox:focus, QTextEdit:focus {
        border: 1px solid ACCENT_COLOR;
    }

    QComboBox::drop-down {
        border: none;
        width: 22px;
    }

    QComboBox QAbstractItemView {
        background-color: PALETTE_CARTE_HAUTE;
        color: PALETTE_TEXTE;
        border: 1px solid PALETTE_BORDURE;
        selection-background-color: ACCENT_COLOR;
        outline: none;
    }

    #boutonPrincipal {
        background-color: ACCENT_COLOR;
        color: white;
        border: none;
        border-radius: 9px;
        font-weight: 600;
        font-size: 13px;
        padding: 10px 16px;
    }

    #boutonPrincipal:hover {
        background-color: ACCENT_HOVER;
    }

    #boutonSecondaire {
        background-color: PALETTE_CARTE_HAUTE;
        color: PALETTE_TEXTE_SECONDAIRE;
        border: 1px solid PALETTE_BORDURE;
        border-radius: 9px;
        font-weight: 500;
        padding: 9px 14px;
    }

    #boutonSecondaire:hover {
        background-color: PALETTE_BORDURE;
        color: PALETTE_TEXTE;
    }

    QTableWidget {
        background-color: PALETTE_CARTE;
        color: PALETTE_TEXTE_ATT;
        border: 1px solid PALETTE_BORDURE;
        border-radius: 12px;
        gridline-color: PALETTE_BORDURE_DOUCE;
        selection-background-color: ACCENT_DOUCE;
        selection-color: PALETTE_TEXTE;
        alternate-background-color: PALETTE_CARTE_HAUTE;
    }

    QTableWidget::item {
        padding: 4px 6px;
        border-bottom: 1px solid PALETTE_BORDURE_DOUCE;
    }

    QHeaderView::section {
        background-color: PALETTE_CARTE_HAUTE;
        color: PALETTE_TEXTE_DISCRET;
        padding: 8px 6px;
        border: none;
        border-bottom: 1px solid PALETTE_BORDURE;
        font-weight: 600;
        font-size: 11.5px;
    }

    QCheckBox {
        color: PALETTE_TEXTE_SECONDAIRE;
        spacing: 8px;
    }

    QToolTip {
        background-color: PALETTE_CARTE_HAUTE;
        color: PALETTE_TEXTE;
        border: 1px solid PALETTE_BORDURE;
        padding: 4px 8px;
        border-radius: 6px;
    }
"""


def creer_bouton_retour_tableau_bord(fenetre):
    """Petit bouton "← Aujourd'hui" à ajouter en haut d'un écran
    secondaire qui n'hérite pas d'EcranListe ni de ConteneurOnglets —
    ferme simplement cette fenêtre (le tableau de bord reste ouvert
    derrière). Réutilise le style #boutonRetourTableauBord défini dans
    obtenir_style_ecran()."""

    bouton = QPushButton("← Aujourd'hui")
    bouton.setObjectName("boutonRetourTableauBord")
    bouton.setCursor(Qt.CursorShape.PointingHandCursor)
    bouton.clicked.connect(fenetre.close)
    return bouton


def obtenir_style_ecran():
    """Retourne la feuille de style avec la couleur d'accent choisie
    dans Réglages (appelée à la construction de chaque écran, pas une
    seule fois à l'import — sinon un changement de couleur ne
    s'appliquerait qu'après redémarrage complet de l'application)."""

    from interface.theme import (
        obtenir_couleur_accent, eclaircir, obtenir_couleur_accent_douce,
        charger_polices, PALETTE, POLICE_TITRE, POLICE_TEXTE,
    )

    charger_polices()

    accent = obtenir_couleur_accent()
    accent_hover = eclaircir(accent)

    return (
        _STYLE_ECRAN_MODELE
        .replace("ACCENT_DOUCE", obtenir_couleur_accent_douce(0.22))
        .replace("ACCENT_COLOR", accent)
        .replace("ACCENT_HOVER", accent_hover)
        .replace("PALETTE_FOND", PALETTE["fond"])
        .replace("PALETTE_CARTE_HAUTE", PALETTE["carte_haute"])
        .replace("PALETTE_CARTE", PALETTE["carte"])
        .replace("PALETTE_BORDURE_DOUCE", PALETTE["bordure_douce"])
        .replace("PALETTE_BORDURE", PALETTE["bordure"])
        .replace("PALETTE_TEXTE_SECONDAIRE", PALETTE["texte_secondaire"])
        .replace("PALETTE_TEXTE_DISCRET", PALETTE["texte_discret"])
        .replace("PALETTE_TEXTE_ATT", PALETTE["texte_att"])
        .replace("PALETTE_TEXTE", PALETTE["texte"])
        .replace("POLICE_TITRE", POLICE_TITRE)
        .replace("POLICE_TEXTE", POLICE_TEXTE)
    )
