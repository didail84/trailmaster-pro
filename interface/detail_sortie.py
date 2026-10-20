"""
Fenêtre de détail d'une sortie — ouverte en double-cliquant sur une
ligne dans l'historique des activités : récapitule tous les chiffres
de la sortie, son tracé (aperçu hors-ligne + lien vers la vraie carte),
les segments détectés et l'analyse IA (Gemini), au même endroit.
"""

import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTextEdit,
    QApplication,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QMessageBox,
)

from data.database import connexion, supprimer_activite
from interface.ecran_liste import obtenir_style_ecran, configurer_table_redimensionnable
from interface.date_utils import parser_date_flexible
from interface.coach import charge_activite_pour_athlete
from interface.vo2max import estimer_vo2max
from interface.trace_widget import TraceCanvas
from interface.photos_ecran import PhotosSortie
from data import photos_sorties
from interface.ia_coach import analyser_sortie, cle_api_configuree
from interface.tache_ia import TacheAnalyseIA


def _formater_duree(secondes):
    if not secondes:
        return "—"
    secondes = int(secondes)
    h, reste = divmod(secondes, 3600)
    m, s = divmod(reste, 60)
    if h > 0:
        return f"{h}h{m:02d}min{s:02d}"
    return f"{m}min{s:02d}"


def _formater_allure(minutes_par_km):
    if not minutes_par_km:
        return "—"
    minutes_par_km = float(minutes_par_km)
    minutes_entieres = int(minutes_par_km)
    secondes = round((minutes_par_km - minutes_entieres) * 60)
    if secondes == 60:
        minutes_entieres += 1
        secondes = 0
    return f"{minutes_entieres}'{secondes:02d}\"/km"


def _valeur(v, unite="", decimales=None):
    if v in (None, ""):
        return "—"
    if decimales is not None:
        return f"{float(v):.{decimales}f}{unite}"
    return f"{v}{unite}"


TYPES_ACTIVITE = ["Trail", "Course", "VTT", "Vélo", "Randonnée", "Route", "Cardio machine", "Autre"]


def _spin_optionnel(minimum, maximum, suffixe="", decimales=None):
    """QSpinBox/QDoubleSpinBox dont la valeur 0 s'affiche « — » (donnée
    manquante) plutôt qu'un « 0 » trompeur — cohérent avec le reste de
    l'appli, où une valeur manquante s'affiche toujours « — »."""

    spin = QDoubleSpinBox() if decimales is not None else QSpinBox()
    spin.setRange(minimum, maximum)
    if decimales is not None:
        spin.setDecimals(decimales)
    if suffixe:
        spin.setSuffix(suffixe)
    spin.setSpecialValueText("—")
    return spin


from interface.outils_ui import notifier


def style_sombre():
    """Feuille de style des écrans « sombres » (D4/D5) : toujours la palette
    sombre, même si le logiciel est en mode clair."""
    from interface.theme import PALETTE, PALETTE_SOMBRE
    sauve = dict(PALETTE)
    PALETTE.update(PALETTE_SOMBRE)
    try:
        return (obtenir_style_ecran()
                + f"QDialog, QWidget#centralDetail {{ background-color: {PALETTE['fond']}; color: {PALETTE['texte']}; }}"
                + f"QScrollArea {{ background-color: {PALETTE['fond']}; border: none; }}")
    finally:
        PALETTE.clear()
        PALETTE.update(sauve)


class StatsFlottantes(QFrame):
    """Chiffres clés posés sur la carte (D4 « carte d'abord »)."""

    def __init__(self, canvas, activite):
        super().__init__(canvas)
        self.setObjectName("statsFlottantes")
        self.setStyleSheet(
            "#statsFlottantes { background-color: rgba(18,21,26,215); border: 1px solid #2B343B; border-radius: 14px; }"
            "QLabel { background: transparent; color: #F3F6F7; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)
        nom = QLabel(activite.get("nom") or activite.get("type") or "Sortie")
        nom.setStyleSheet("font-size:16px; font-weight:800;")
        lay.addWidget(nom)
        d = parser_date_flexible(activite.get("date"))
        sous = QLabel((d.strftime("%d/%m/%Y %H:%M") if d else "") + (f" · {activite['type']}" if activite.get("type") else ""))
        sous.setStyleSheet("font-size:11px; color:#9AA7AE;")
        lay.addWidget(sous)
        grille = QHBoxLayout()
        grille.setSpacing(18)
        morceaux = [
            ("DISTANCE", f"{activite['distance']:.1f} km" if activite.get("distance") else "—"),
            ("D+", f"{int(activite['denivele'])} m" if activite.get("denivele") else "—"),
            ("DURÉE", _formater_duree(activite.get("duree"))),
            ("ALLURE", _formater_allure(activite.get("allure_moyenne"))),
            ("FC MOY", f"{int(activite['frequence_cardiaque_moyenne'])} bpm" if activite.get("frequence_cardiaque_moyenne") else "—"),
        ]
        for lib, val in morceaux:
            bloc = QVBoxLayout()
            bloc.setSpacing(0)
            a = QLabel(lib)
            a.setStyleSheet("font-size:9px; font-weight:700; color:#6B767D;")
            b = QLabel(val)
            b.setStyleSheet("font-size:17px; font-weight:800;")
            bloc.addWidget(a)
            bloc.addWidget(b)
            grille.addLayout(bloc)
        lay.addLayout(grille)
        self.adjustSize()
        self.move(16, 16)
        self.raise_()


class DialogueDetailSortie(QDialog):

    def __init__(self, activite_id, athlete_id, parent=None, au_enregistrement=None):
        super().__init__(parent)
        self.activite_id = activite_id
        self.athlete_id = athlete_id
        self._au_enregistrement = au_enregistrement

        self.setWindowTitle("Détail de la sortie")
        self.resize(1150, 900)
        self.setMinimumSize(850, 600)

        layout_externe = QVBoxLayout(self)
        layout_externe.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout_externe.addWidget(scroll)

        central = QWidget()
        central.setObjectName("centralDetail")
        scroll.setWidget(central)

        principal = QVBoxLayout(central)
        principal.setContentsMargins(25, 20, 25, 20)
        principal.setSpacing(18)

        activite = self._charger_activite()
        if activite is None:
            principal.addWidget(QLabel("Sortie introuvable."))
            self.setStyleSheet(obtenir_style_ecran())
            return

        # ------------------------------------------------------------
        # EN-TÊTE (nom, type, date — modifiables)
        # ------------------------------------------------------------

        date_obj = parser_date_flexible(activite["date"])
        date_texte = date_obj.strftime("%d/%m/%Y %H:%M") if date_obj else (activite["date"] or "")

        titre = QLabel("🏃 Détail de la sortie")
        titre.setObjectName("titrePage")
        sous_titre = QLabel(
            "Les champs manquants (« — ») peuvent être complétés ci-dessous, puis "
            "enregistrés avec le bouton en bas de cette carte."
        )
        sous_titre.setObjectName("sousTitrePage")
        sous_titre.setWordWrap(True)
        principal.addWidget(titre)
        principal.addWidget(sous_titre)

        cadre_entete = QFrame()
        cadre_entete.setObjectName("carteForm")
        entete_layout = QGridLayout(cadre_entete)
        entete_layout.setHorizontalSpacing(20)
        entete_layout.setVerticalSpacing(8)

        self.champ_nom = QLineEdit(activite["nom"] or "")
        self.champ_type = QComboBox()
        self.champ_type.setEditable(True)
        self.champ_type.addItems(TYPES_ACTIVITE)
        self.champ_type.setCurrentText(activite["type"] or "")
        self.champ_date = QLineEdit(date_texte)
        self.champ_date.setPlaceholderText("JJ/MM/AAAA HH:MM")
        self.champ_source = QLineEdit(activite["source"] or "")

        for col, (label, widget) in enumerate([
            ("Nom", self.champ_nom), ("Type", self.champ_type),
            ("Date", self.champ_date), ("Source", self.champ_source),
        ]):
            lbl = QLabel(label)
            lbl.setObjectName("texteSecondaire")
            entete_layout.addWidget(lbl, 0, col)
            entete_layout.addWidget(widget, 1, col)

        principal.addWidget(cadre_entete)

        # ------------------------------------------------------------
        # CHIFFRES CLÉS (modifiables)
        # ------------------------------------------------------------

        cadre_chiffres = QFrame()
        cadre_chiffres.setObjectName("carteForm")
        chiffres_layout = QVBoxLayout(cadre_chiffres)

        titre_chiffres = QLabel("📊 Chiffres de la sortie")
        titre_chiffres.setObjectName("titreCarte")
        chiffres_layout.addWidget(titre_chiffres)

        grille = QGridLayout()
        grille.setHorizontalSpacing(24)
        grille.setVerticalSpacing(12)
        chiffres_layout.addLayout(grille)

        self.champ_distance = _spin_optionnel(0, 500, " km", decimales=2)
        self.champ_distance.setValue(activite["distance"] or 0)

        self.champ_denivele = _spin_optionnel(0, 20000, " m")
        self.champ_denivele.setValue(activite["denivele"] or 0)
        self.champ_denivele_neg = _spin_optionnel(0, 20000, " m")
        self.champ_denivele_neg.setValue(activite["denivele_negatif"] or 0)

        duree_s = int(activite["duree"] or 0)
        h, reste = divmod(duree_s, 3600)
        m, s = divmod(reste, 60)
        self.champ_duree_h = QSpinBox(); self.champ_duree_h.setRange(0, 99); self.champ_duree_h.setSuffix(" h"); self.champ_duree_h.setValue(h)
        self.champ_duree_m = QSpinBox(); self.champ_duree_m.setRange(0, 59); self.champ_duree_m.setSuffix(" min"); self.champ_duree_m.setValue(m)
        self.champ_duree_s = QSpinBox(); self.champ_duree_s.setRange(0, 59); self.champ_duree_s.setSuffix(" s"); self.champ_duree_s.setValue(s)
        bloc_duree = QWidget()
        bloc_duree_layout = QHBoxLayout(bloc_duree)
        bloc_duree_layout.setContentsMargins(0, 0, 0, 0)
        bloc_duree_layout.addWidget(self.champ_duree_h)
        bloc_duree_layout.addWidget(self.champ_duree_m)
        bloc_duree_layout.addWidget(self.champ_duree_s)

        def _bloc_allure(valeur_min_par_km):
            valeur = valeur_min_par_km or 0
            m_ = int(valeur)
            s_ = round((valeur - m_) * 60) if valeur else 0
            champ_m = QSpinBox(); champ_m.setRange(0, 59); champ_m.setSuffix("'")
            champ_s = QSpinBox(); champ_s.setRange(0, 59); champ_s.setSuffix('"')
            champ_m.setValue(m_)
            champ_s.setValue(s_)
            bloc = QWidget()
            bloc_layout = QHBoxLayout(bloc)
            bloc_layout.setContentsMargins(0, 0, 0, 0)
            bloc_layout.addWidget(champ_m)
            bloc_layout.addWidget(champ_s)
            return bloc, champ_m, champ_s

        bloc_allure_moy, self.champ_allure_moy_m, self.champ_allure_moy_s = _bloc_allure(activite["allure_moyenne"])
        bloc_allure_max, self.champ_allure_max_m, self.champ_allure_max_s = _bloc_allure(activite["allure_max"])

        self.champ_vitesse_moy = _spin_optionnel(0, 100, " km/h", decimales=2)
        self.champ_vitesse_moy.setValue(activite["vitesse_moyenne"] or 0)
        self.champ_vitesse_max = _spin_optionnel(0, 100, " km/h", decimales=2)
        self.champ_vitesse_max.setValue(activite["vitesse_max"] or 0)

        # Remplissage automatique de l'allure moyenne et de la vitesse
        # moyenne dès que la distance et/ou la durée sont connues —
        # recalculées à chaque changement de l'une ou l'autre, pour
        # éviter d'avoir à les recopier à la main. Un utilisateur qui
        # veut une valeur différente peut toujours la retoucher ensuite
        # (elle sera simplement recalculée s'il retouche encore la
        # distance ou la durée).
        self.champ_distance.valueChanged.connect(self._recalculer_allure_et_vitesse_moyennes)
        self.champ_duree_h.valueChanged.connect(self._recalculer_allure_et_vitesse_moyennes)
        self.champ_duree_m.valueChanged.connect(self._recalculer_allure_et_vitesse_moyennes)
        self.champ_duree_s.valueChanged.connect(self._recalculer_allure_et_vitesse_moyennes)

        # Si l'allure et/ou la vitesse moyennes ne sont pas encore
        # renseignées mais que la distance et la durée le sont déjà
        # (import sans ces champs, saisie manuelle partielle...), on les
        # calcule tout de suite à l'ouverture — sans écraser des valeurs
        # déjà présentes (par ex. venant d'un fichier GPS précis).
        if not (activite["allure_moyenne"] or 0) or not (activite["vitesse_moyenne"] or 0):
            self._recalculer_allure_et_vitesse_moyennes()

        self.champ_fc_moy = _spin_optionnel(0, 250, " bpm")
        self.champ_fc_moy.setValue(activite["frequence_cardiaque_moyenne"] or 0)
        self.champ_fc_max = _spin_optionnel(0, 250, " bpm")
        self.champ_fc_max.setValue(activite["frequence_cardiaque_max"] or 0)

        self.champ_cadence = _spin_optionnel(0, 250, " spm")
        self.champ_cadence.setValue(activite["cadence_moyenne"] or 0)

        self.champ_calories = _spin_optionnel(0, 20000, "")
        self.champ_calories.setValue(activite["calories"] or 0)

        self.champ_vo2max = _spin_optionnel(0, 90, "", decimales=1)
        self.champ_vo2max.setValue(activite["vo2max"] or 0)

        charge, _methode = charge_activite_pour_athlete(
            {"type": activite["type"], "distance": activite["distance"], "duree": activite["duree"],
             "frequence_cardiaque_moyenne": activite["frequence_cardiaque_moyenne"]},
            athlete_id,
        )
        vo2max_affiche = activite["vo2max"] or estimer_vo2max(activite["distance"], activite["duree"])
        self.label_charge_calculee = QLabel(
            f"Charge (TRIMP) calculée : {_valeur(charge, '', 1)}   ·   "
            f"VO2max affiché ailleurs si non renseigné ici : {_valeur(vo2max_affiche, '', 1)}"
        )
        self.label_charge_calculee.setObjectName("texteSecondaire")
        self.label_charge_calculee.setWordWrap(True)

        champs_grille = [
            ("Distance", self.champ_distance), ("D+", self.champ_denivele), ("D−", self.champ_denivele_neg),
            ("Durée", bloc_duree), ("Allure moyenne (/km)", bloc_allure_moy), ("Allure max (/km)", bloc_allure_max),
            ("Vitesse moyenne", self.champ_vitesse_moy), ("Vitesse max", self.champ_vitesse_max),
            ("FC moyenne", self.champ_fc_moy), ("FC max", self.champ_fc_max),
            ("Cadence moyenne", self.champ_cadence), ("Calories", self.champ_calories),
            ("VO2max (mesuré)", self.champ_vo2max),
        ]
        for i, (label, widget) in enumerate(champs_grille):
            colonne = i % 4
            ligne = (i // 4) * 2
            lbl = QLabel(label)
            lbl.setObjectName("texteSecondaire")
            grille.addWidget(lbl, ligne, colonne)
            grille.addWidget(widget, ligne + 1, colonne)

        chiffres_layout.addWidget(self.label_charge_calculee)

        barre_enregistrer = QHBoxLayout()
        self.bouton_enregistrer = QPushButton("💾 Enregistrer les modifications")
        self.bouton_enregistrer.setObjectName("boutonPrincipal")
        self.bouton_enregistrer.clicked.connect(self._enregistrer_modifications)
        barre_enregistrer.addStretch()
        barre_enregistrer.addWidget(self.bouton_enregistrer)
        chiffres_layout.addLayout(barre_enregistrer)

        principal.addWidget(cadre_chiffres)

        cadre_avance = self._construire_detail_avance(activite)
        if cadre_avance is not None:
            principal.addWidget(cadre_avance)

        cadre_notes = QFrame()
        cadre_notes.setObjectName("carteForm")
        notes_layout = QVBoxLayout(cadre_notes)
        titre_notes = QLabel("📝 Notes")
        titre_notes.setObjectName("titreCarte")
        notes_layout.addWidget(titre_notes)
        self.champ_notes = QTextEdit(activite["notes"] or "")
        self.champ_notes.setMinimumHeight(80)
        self.champ_notes.setMaximumHeight(140)
        notes_layout.addWidget(self.champ_notes)
        principal.addWidget(cadre_notes)

        # ------------------------------------------------------------
        # TRACÉ / CARTE
        # ------------------------------------------------------------

        cadre_trace = QFrame()
        cadre_trace.setObjectName("carteForm")
        trace_layout = QVBoxLayout(cadre_trace)
        titre_trace = QLabel("🗺️ Tracé")
        titre_trace.setObjectName("titreCarte")
        trace_layout.addWidget(titre_trace)

        parcours = self._charger_parcours_lie()
        if parcours is not None:
            canvas = TraceCanvas()
            canvas.setMinimumHeight(480)
            StatsFlottantes(canvas, activite)
            points = json.loads(parcours["trace_json"])
            points_2d = [(p[0], p[1]) for p in points]
            altitudes = [p[2] if len(p) > 2 else 0 for p in points]
            canvas.definir_trace(points_2d, altitudes)
            trace_layout.addWidget(canvas)

            # Meilleures portions / secteurs : demande une trace avec le temps de chaque point
            avec_temps = sum(1 for p in points if len(p) > 3 and p[3] is not None)
            if avec_temps >= 20:
                bouton_portions = QPushButton("🏅 Meilleures portions et secteurs (sur la carte)")
                bouton_portions.setObjectName("boutonPrincipal")
                bouton_portions.clicked.connect(lambda: self._ouvrir_meilleures_portions(points))
                trace_layout.addWidget(bouton_portions)
            else:
                trace_layout.addWidget(QLabel(
                    "Les meilleures portions demandent une trace GPS avec l'heure de chaque "
                    "point (fichier FIT ou GPX de la montre) : celle-ci n'en contient pas."))

            bouton_carte_reelle = QPushButton("🗺️ Voir sur la carte réelle (rues, relief)")
            bouton_carte_reelle.setObjectName("boutonSecondaire")
            bouton_carte_reelle.clicked.connect(lambda: self._ouvrir_carte_reelle(parcours["id"]))
            trace_layout.addWidget(bouton_carte_reelle)
        else:
            trace_layout.addWidget(QLabel(
                "Aucun tracé GPS disponible pour cette sortie (pas de trace importée ou "
                "liée à cette activité)."
            ))

        principal.insertWidget(0, cadre_trace)   # D4 : la carte d'abord

        # S8 — ressenti en 3 clics
        from interface.ressenti import BandeauRessenti
        principal.addWidget(BandeauRessenti(self.activite_id, self.athlete_id, activite.get("nom") or ""))
        bouton_partage = QPushButton("🖼️ Fiche à partager en image")
        bouton_partage.setObjectName("boutonSecondaire")
        bouton_partage.clicked.connect(self._partager_image)
        principal.addWidget(bouton_partage, 0, Qt.AlignmentFlag.AlignLeft)

        # ------------------------------------------------------------
        # PHOTOS
        # ------------------------------------------------------------

        self._canvas_trace = canvas if parcours is not None else None
        self._points_trace = points if parcours is not None else None
        self._debut_activite = activite.get("date")
        self.zone_photos = PhotosSortie(self.activite_id, self.athlete_id, self._placer_photos_sur_carte)
        principal.addWidget(self.zone_photos)
        if self._canvas_trace is not None:
            self._canvas_trace.marqueur_clique.connect(self._photo_marqueur_cliquee)
        self._placer_photos_sur_carte()

        # ------------------------------------------------------------
        # SEGMENTS
        # ------------------------------------------------------------

        cadre_segments = QFrame()
        cadre_segments.setObjectName("carteForm")
        segments_layout = QVBoxLayout(cadre_segments)
        titre_segments = QLabel("⏱️ Segments")
        titre_segments.setObjectName("titreCarte")
        segments_layout.addWidget(titre_segments)

        efforts = self._charger_segments_efforts()
        if efforts:
            table_segments = QTableWidget()
            table_segments.setColumnCount(3)
            table_segments.setHorizontalHeaderLabels(["Segment", "Distance (km)", "Temps"])
            configurer_table_redimensionnable(table_segments)
            table_segments.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table_segments.setRowCount(len(efforts))
            for i, (nom, distance_km, duree_s) in enumerate(efforts):
                table_segments.setItem(i, 0, QTableWidgetItem(nom or "—"))
                table_segments.setItem(i, 1, QTableWidgetItem(_valeur(distance_km, " km", 2)))
                table_segments.setItem(i, 2, QTableWidgetItem(_formater_duree(duree_s)))
            table_segments.setMinimumHeight(min(200, 40 + 30 * len(efforts)))
            segments_layout.addWidget(table_segments)
        else:
            segments_layout.addWidget(QLabel("Aucun segment détecté pour cette sortie."))

        principal.addWidget(cadre_segments)

        # ------------------------------------------------------------
        # ANALYSE IA
        # ------------------------------------------------------------

        cadre_ia = QFrame()
        cadre_ia.setObjectName("carteForm")
        ia_layout = QVBoxLayout(cadre_ia)
        titre_ia = QLabel("🤖 Avis et conseils de l'IA")
        titre_ia.setObjectName("titreCarte")
        ia_layout.addWidget(titre_ia)

        self.zone_texte_ia = QTextEdit()
        self.zone_texte_ia.setReadOnly(True)
        self.zone_texte_ia.setMinimumHeight(280)
        ia_layout.addWidget(self.zone_texte_ia)

        barre_ia = QHBoxLayout()
        self.bouton_regenerer_ia = QPushButton("🤖 Générer / régénérer l'analyse")
        self.bouton_regenerer_ia.setObjectName("boutonSecondaire")
        self.bouton_regenerer_ia.clicked.connect(lambda: self._lancer_analyse_ia(forcer=True))
        barre_ia.addWidget(self.bouton_regenerer_ia)
        barre_ia.addStretch()
        ia_layout.addLayout(barre_ia)

        principal.addWidget(cadre_ia)

        barre_bas = QHBoxLayout()
        bouton_supprimer = QPushButton("🗑 Supprimer cette sortie")
        bouton_supprimer.setObjectName("boutonSecondaire")
        bouton_supprimer.clicked.connect(self._supprimer_sortie)
        barre_bas.addWidget(bouton_supprimer)
        barre_bas.addStretch()

        bouton_fermer = QPushButton("Fermer")
        bouton_fermer.setObjectName("boutonSecondaire")
        bouton_fermer.clicked.connect(self.accept)
        barre_bas.addWidget(bouton_fermer)

        principal.addLayout(barre_bas)

        self.setStyleSheet(style_sombre())

        # U9 — Alt+← / Alt+→ : sortie précédente / suivante
        QShortcut(QKeySequence("Alt+Left"), self, activated=lambda: self._naviguer(-1))
        QShortcut(QKeySequence("Alt+Right"), self, activated=lambda: self._naviguer(1))

        self._afficher_analyse_en_cache()

    def _naviguer(self, sens):
        conn = connexion()
        cur = conn.cursor()
        cur.execute("SELECT id FROM activites WHERE athlete_id=? ORDER BY date, id", (self.athlete_id,))
        ids = [r[0] for r in cur.fetchall()]
        conn.close()
        if self.activite_id not in ids:
            return
        i = ids.index(self.activite_id) + sens
        if not 0 <= i < len(ids):
            return
        parent, cb, athlete, cible = self.parent(), self._au_enregistrement, self.athlete_id, ids[i]
        self.accept()
        QTimer.singleShot(0, lambda: DialogueDetailSortie(cible, athlete, parent=parent, au_enregistrement=cb).exec())

    def _afficher_analyse_en_cache(self):
        """À l'ouverture : montre l'analyse déjà générée, sans rien
        télécharger (la génération ne part que sur clic, pour ne pas
        consommer le quota gratuit de l'IA à chaque sortie ouverte)."""
        from interface.ia_coach import _analyse_en_cache
        trouve = _analyse_en_cache(self.activite_id)
        if trouve:
            self._analyse_ia_reussie((trouve[0], True))
        elif cle_api_configuree():
            self.zone_texte_ia.setPlainText("Pas encore d'analyse pour cette sortie : clique sur « Générer l'analyse ».")
        else:
            self._lancer_analyse_ia(forcer=False)   # affiche le message « aucune clé API »

    def _supprimer_sortie(self):
        confirmation = QMessageBox.question(
            self,
            "Confirmer la suppression",
            "Voulez-vous vraiment supprimer cette sortie ?\n\n"
            "La trace GPS, les efforts sur segments et le compte rendu IA associés "
            "seront supprimés avec elle. Une séance planifiée liée redeviendra "
            "\"Prévue\" plutôt que d'être supprimée.\n\n"
            "Cette action est irréversible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        try:
            supprimer_activite(self.activite_id)
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur de suppression",
                f"Impossible de supprimer cette sortie.\n\n{e}"
            )
            return

        if self._au_enregistrement:
            self._au_enregistrement()
        self.accept()

    # ------------------------------------------------------------
    # REMPLISSAGE AUTOMATIQUE ALLURE / VITESSE MOYENNES
    # ------------------------------------------------------------

    def _recalculer_allure_et_vitesse_moyennes(self):
        """Recalcule l'allure moyenne (min/km) et la vitesse moyenne
        (km/h) à partir de la distance et de la durée saisies. Ne fait
        rien tant que l'une des deux n'est pas encore renseignée."""

        distance_km = self.champ_distance.value()
        duree_s = (
            self.champ_duree_h.value() * 3600
            + self.champ_duree_m.value() * 60
            + self.champ_duree_s.value()
        )
        if not distance_km or not duree_s:
            return

        duree_h = duree_s / 3600
        vitesse_kmh = distance_km / duree_h
        allure_min_par_km = (duree_s / 60) / distance_km

        # Bloque temporairement les signaux le temps de mettre à jour
        # les champs, pour éviter tout rebouclage inutile.
        allure_m = int(allure_min_par_km)
        allure_s = round((allure_min_par_km - allure_m) * 60)
        if allure_s == 60:
            allure_m += 1
            allure_s = 0

        self.champ_allure_moy_m.blockSignals(True)
        self.champ_allure_moy_s.blockSignals(True)
        self.champ_allure_moy_m.setValue(allure_m)
        self.champ_allure_moy_s.setValue(allure_s)
        self.champ_allure_moy_m.blockSignals(False)
        self.champ_allure_moy_s.blockSignals(False)

        self.champ_vitesse_moy.blockSignals(True)
        self.champ_vitesse_moy.setValue(round(vitesse_kmh, 2))
        self.champ_vitesse_moy.blockSignals(False)

    # ------------------------------------------------------------
    # CHARGEMENT DES DONNÉES
    # ------------------------------------------------------------

    def _charger_activite(self):
        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "SELECT date, nom, type, distance, denivele, denivele_negatif, duree, "
            "vitesse_moyenne, vitesse_max, allure_moyenne, allure_max, "
            "frequence_cardiaque_moyenne, frequence_cardiaque_max, calories, "
            "cadence_moyenne, vo2max, source, notes, "
            "te_aerobie, te_anaerobie, charge_garmin, "
            "temps_zone_1, temps_zone_2, temps_zone_3, temps_zone_4, temps_zone_5, "
            "puissance_moyenne, puissance_max, oscillation_verticale, temps_contact_sol, "
            "longueur_foulee, temperature_moyenne, effort_percu, suffer_score "
            "FROM activites WHERE id=? AND athlete_id=?",
            (self.activite_id, self.athlete_id),
        )
        ligne = cur.fetchone()
        conn.close()
        if not ligne:
            return None

        cles = [
            "date", "nom", "type", "distance", "denivele", "denivele_negatif", "duree",
            "vitesse_moyenne", "vitesse_max", "allure_moyenne", "allure_max",
            "frequence_cardiaque_moyenne", "frequence_cardiaque_max", "calories",
            "cadence_moyenne", "vo2max", "source", "notes",
            "te_aerobie", "te_anaerobie", "charge_garmin",
            "temps_zone_1", "temps_zone_2", "temps_zone_3", "temps_zone_4", "temps_zone_5",
            "puissance_moyenne", "puissance_max", "oscillation_verticale", "temps_contact_sol",
            "longueur_foulee", "temperature_moyenne", "effort_percu", "suffer_score",
        ]
        return dict(zip(cles, ligne))

    def _construire_detail_avance(self, activite):
        """Carte « Détail avancé » (lecture seule) : effet d'entraînement,
        zones de FC, puissance, dynamique de course, température, effort
        perçu, efficience, dérive cardiaque. None si rien à afficher."""
        def duree_courte(sec):
            sec = int(sec or 0)
            h, r = divmod(sec, 3600)
            m, s = divmod(r, 60)
            return f"{h} h {m:02d}" if h else f"{m} min {s:02d}"

        infos = []
        if activite.get("te_aerobie") is not None:
            infos.append(("Effet d'entraînement aérobie", f"{activite['te_aerobie']:.1f} / 5"))
        if activite.get("te_anaerobie") is not None:
            infos.append(("Effet d'entraînement anaérobie", f"{activite['te_anaerobie']:.1f} / 5"))
        if activite.get("charge_garmin") is not None:
            infos.append(("Charge Garmin", f"{activite['charge_garmin']:.0f}"))
        zones = [activite.get(f"temps_zone_{i}") for i in range(1, 6)]
        if any(zones):
            total = sum(z or 0 for z in zones) or 1
            infos.append(("Temps par zone de FC", "  ·  ".join(
                f"Z{i} {duree_courte(z)} ({round((z or 0) / total * 100)} %)"
                for i, z in enumerate(zones, 1) if z)))
        if activite.get("puissance_moyenne"):
            p = f"{activite['puissance_moyenne']} W"
            if activite.get("puissance_max"):
                p += f" (max {activite['puissance_max']} W)"
            infos.append(("Puissance moyenne", p))
        if activite.get("oscillation_verticale"):
            infos.append(("Oscillation verticale", f"{activite['oscillation_verticale']:.1f} cm"))
        if activite.get("temps_contact_sol"):
            infos.append(("Temps de contact au sol", f"{activite['temps_contact_sol']} ms"))
        if activite.get("longueur_foulee"):
            infos.append(("Longueur de foulée", f"{activite['longueur_foulee']:.2f} m"))
        if activite.get("temperature_moyenne") is not None:
            infos.append(("Température moyenne", f"{activite['temperature_moyenne']:.0f} °C"))
        if activite.get("effort_percu") is not None:
            infos.append(("Effort perçu (Strava)", f"{activite['effort_percu']:g} / 10"))
        if activite.get("suffer_score") is not None:
            infos.append(("Effort relatif (Strava)", f"{activite['suffer_score']}"))

        try:
            from interface.recuperation_tendances import efficience
            e = efficience({
                "distance": activite.get("distance"), "duree": activite.get("duree"),
                "denivele": activite.get("denivele"), "fc_moy": activite.get("frequence_cardiaque_moyenne"),
            })
            if e is not None and activite.get("type") in ("Trail", "Course"):
                infos.append(("Efficience (m/min par battement)", f"{e:.2f}"))
        except Exception:
            pass

        try:
            parcours = self._charger_parcours_lie()
            if parcours:
                import json as _json
                from interface.dynamique_course import calculer_decouplage_cardiaque
                dec = calculer_decouplage_cardiaque(_json.loads(parcours["trace_json"]))
                if dec:
                    infos.append(("Dérive cardiaque", f"{dec['decouplage_pct']:+.1f} % — {dec['interpretation']}"))
        except Exception:
            pass

        if not infos:
            return None

        cadre = QFrame()
        cadre.setObjectName("carteForm")
        lay = QVBoxLayout(cadre)
        titre = QLabel("🔬 Détail avancé")
        titre.setObjectName("titreCarte")
        lay.addWidget(titre)
        grille = QGridLayout()
        grille.setHorizontalSpacing(24)
        grille.setVerticalSpacing(6)
        for i, (lib, val) in enumerate(infos):
            l1 = QLabel(lib)
            l1.setObjectName("texteSecondaire")
            l2 = QLabel(val)
            l2.setWordWrap(True)
            grille.addWidget(l1, i, 0)
            grille.addWidget(l2, i, 1)
        grille.setColumnStretch(1, 1)
        lay.addLayout(grille)
        return cadre

    def _partager_image(self):
        from interface.partage_images import DialogueFicheSortie
        DialogueFicheSortie(self.activite_id, self).exec()

    def _placer_photos_sur_carte(self):
        """Pastilles numérotées sur le tracé pour les photos qu'on peut situer."""
        if self._canvas_trace is None:
            return
        self._photos_sur_carte = []
        marqueurs = []
        for i, p in enumerate(self.zone_photos.photos):
            pos = photos_sorties.position_sur_trace(p, self._points_trace, self._debut_activite)
            if pos:
                self._photos_sur_carte.append(i)
                marqueurs.append((pos[0], pos[1], p.get("legende") or f"Photo {i + 1}"))
        self._canvas_trace.definir_marqueurs(marqueurs)

    def _photo_marqueur_cliquee(self, indice):
        if 0 <= indice < len(self._photos_sur_carte):
            self.zone_photos.ouvrir_photo(self._photos_sur_carte[indice])

    def _charger_parcours_lie(self):
        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, trace_json FROM parcours_gpx WHERE activite_id=? AND trace_json IS NOT NULL",
            (self.activite_id,),
        )
        resultat = cur.fetchone()
        conn.close()
        if not resultat or not resultat[1]:
            return None
        return {"id": resultat[0], "trace_json": resultat[1]}

    def _charger_segments_efforts(self):
        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            "SELECT s.nom, s.distance_km, e.duree_s FROM segments_efforts e "
            "JOIN segments s ON e.segment_id = s.id "
            "WHERE e.activite_id=?",
            (self.activite_id,),
        )
        lignes = cur.fetchall()
        conn.close()
        return lignes

    def _ouvrir_meilleures_portions(self, points):
        from interface.meilleures_portions import ouvrir_meilleures_portions
        ouvrir_meilleures_portions(
            self, points, self.champ_nom.text().strip() if hasattr(self, "champ_nom") else "",
            self.champ_type.currentText().strip(),
        )

    def _ouvrir_carte_reelle(self, parcours_id):
        from interface.carte_reelle import CarteReelle
        self._fenetre_carte = CarteReelle(athlete_id_initial=self.athlete_id, parcours_id_initial=parcours_id)
        self._fenetre_carte.show()

    def _enregistrer_modifications(self):
        date_obj = parser_date_flexible(self.champ_date.text().strip())
        if date_obj is None:
            QMessageBox.warning(
                self, "Date invalide",
                "Le format de la date n'est pas reconnu — utilise JJ/MM/AAAA HH:MM."
            )
            return

        duree_s = (
            self.champ_duree_h.value() * 3600
            + self.champ_duree_m.value() * 60
            + self.champ_duree_s.value()
        )

        def _allure(champ_m, champ_s):
            m, s = champ_m.value(), champ_s.value()
            return round(m + s / 60, 3) if (m or s) else None

        def _zero_en_none(spin):
            valeur = spin.value()
            return None if not valeur else valeur

        colonnes_valeurs = [
            ("nom", self.champ_nom.text().strip() or None),
            ("type", self.champ_type.currentText().strip() or None),
            ("date", date_obj.strftime("%Y-%m-%d %H:%M:%S")),
            ("source", self.champ_source.text().strip() or None),
            ("distance", _zero_en_none(self.champ_distance)),
            ("denivele", _zero_en_none(self.champ_denivele)),
            ("denivele_negatif", _zero_en_none(self.champ_denivele_neg)),
            ("duree", duree_s or None),
            ("allure_moyenne", _allure(self.champ_allure_moy_m, self.champ_allure_moy_s)),
            ("allure_max", _allure(self.champ_allure_max_m, self.champ_allure_max_s)),
            ("vitesse_moyenne", _zero_en_none(self.champ_vitesse_moy)),
            ("vitesse_max", _zero_en_none(self.champ_vitesse_max)),
            ("frequence_cardiaque_moyenne", _zero_en_none(self.champ_fc_moy)),
            ("frequence_cardiaque_max", _zero_en_none(self.champ_fc_max)),
            ("cadence_moyenne", _zero_en_none(self.champ_cadence)),
            ("calories", _zero_en_none(self.champ_calories)),
            ("vo2max", _zero_en_none(self.champ_vo2max)),
            ("notes", self.champ_notes.toPlainText().strip() or None),
        ]

        affectations = ", ".join(f"{nom}=?" for nom, _ in colonnes_valeurs)
        valeurs = [valeur for _, valeur in colonnes_valeurs] + [self.activite_id, self.athlete_id]

        conn = connexion()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE activites SET {affectations} WHERE id=? AND athlete_id=?",
            valeurs,
        )
        conn.commit()
        conn.close()

        # Rafraîchit la charge affichée (recalculée à partir des nouvelles
        # valeurs) sans avoir à fermer/rouvrir la fenêtre.
        activite_maj = self._charger_activite()
        if activite_maj is not None:
            charge, _methode = charge_activite_pour_athlete(
                {"type": activite_maj["type"], "distance": activite_maj["distance"],
                 "duree": activite_maj["duree"],
                 "frequence_cardiaque_moyenne": activite_maj["frequence_cardiaque_moyenne"]},
                self.athlete_id,
            )
            vo2max_affiche = activite_maj["vo2max"] or estimer_vo2max(activite_maj["distance"], activite_maj["duree"])
            self.label_charge_calculee.setText(
                f"Charge (TRIMP) calculée : {_valeur(charge, '', 1)}   ·   "
                f"VO2max affiché ailleurs si non renseigné ici : {_valeur(vo2max_affiche, '', 1)}"
            )

        if self._au_enregistrement:
            self._au_enregistrement()

        notifier("Modifications enregistrées", parent=self)

    def _lancer_analyse_ia(self, forcer):
        if not cle_api_configuree():
            self.zone_texte_ia.setPlainText(
                "⚠️ Aucune clé API configurée.\n\n"
                "Va dans Réglages > Analyse IA des sorties pour renseigner une clé "
                "gratuite (Gemini et/ou Groq), puis reviens ici."
            )
            self.bouton_regenerer_ia.setEnabled(False)
            return

        self.zone_texte_ia.setPlainText(
            "⏳ Génération de l'analyse en cours... (nécessite une connexion internet — "
            "la fenêtre reste utilisable pendant l'attente)"
            if forcer else
            "⏳ Chargement de l'analyse..."
        )
        self.bouton_regenerer_ia.setEnabled(False)

        self._tache_analyse_ia = TacheAnalyseIA(
            lambda: analyser_sortie(self.activite_id, self.athlete_id, forcer_regeneration=forcer)
        )
        self._tache_analyse_ia.reussite.connect(self._analyse_ia_reussie)
        self._tache_analyse_ia.echec.connect(self._analyse_ia_echouee)
        self._tache_analyse_ia.start()

    def _analyse_ia_reussie(self, resultat):
        contenu, depuis_cache = resultat
        entete = "📦 Analyse déjà générée précédemment (mise en cache) :\n\n" if depuis_cache else ""
        self.zone_texte_ia.setPlainText(entete + contenu)
        self.bouton_regenerer_ia.setEnabled(True)

    def _analyse_ia_echouee(self, message):
        self.zone_texte_ia.setPlainText(f"⚠️ {message}")
        self.bouton_regenerer_ia.setEnabled(True)
