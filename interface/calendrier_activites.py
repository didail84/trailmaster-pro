"""
Calendrier des sorties — vue à la semaine, au mois ou à l'année.

- Semaine : 7 colonnes, chaque sortie du jour est affichée avec son détail
  (distance, D+, durée, allure, FC) ; un clic l'ouvre.
- Mois : une grille classique, les sorties de chaque jour sont des boutons
  cliquables.
- Année : les 12 mois d'un coup, un carré par jour (couleur = type de
  sortie), pour repérer d'un coup d'œil les semaines chargées et les
  périodes de repos ; un clic sur un jour l'ouvre, un clic sur le nom
  d'un mois affiche ce mois.

Les jours sans aucune activité enregistrée sont des jours de repos : rien
n'est stocké pour eux, c'est simplement l'absence de sortie. Un clic sur
un jour de repos permet de saisir la sortie oubliée. Les séances de
musculation enregistrées (suivi musculation) apparaissent aussi sur le
jour concerné.
"""

import calendar
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QMenu, QMessageBox, QScrollArea, QWidget, QSizePolicy,
)

from data.database import connexion
from interface.theme import (
    PALETTE, POLICE_TITRE, POLICE_TEXTE, POLICE_TEXTE_DEMI,
    obtenir_couleur_accent, obtenir_couleur_accent_douce,
)
from interface.detail_sortie import DialogueDetailSortie
from interface.dialogue_nouvelle_activite import DialogueNouvelleActivite


NOMS_JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
NOMS_MOIS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

ICONES_TYPE = {
    "Trail": "⛰️", "Course": "🏃", "VTT": "🚵", "Vélo": "🚴",
    "Randonnée": "🥾", "Route": "🏃", "Cardio machine": "🏋️",
    "Musculation": "🏋️",
}

COULEURS_TYPE = {
    "Trail": "#F9A825", "Course": "#42A5F5", "Randonnée": "#66BB6A",
    "VTT": "#AB47BC", "Vélo": "#26A69A", "Musculation": "#EF5350",
}
COULEUR_AUTRE = "#8A949B"

MODES = ("Semaine", "Mois", "Année")


def _formater_duree_courte(secondes):
    if not secondes:
        return ""
    minutes = round(secondes / 60)
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}"


def _allure_texte(distance, duree):
    if not distance or distance < 0.5 or not duree:
        return ""
    sec = int(round(duree / distance))
    return f"{sec // 60}:{sec % 60:02d}/km"


def _lundi(jour):
    return jour - timedelta(days=jour.weekday())


def charger_jours(athlete_id, debut_iso, fin_iso):
    """Retourne {jour_iso: [entrée, ...]} où chaque entrée est un dict :
    sortie  -> {"genre": "sortie", "id", "nom", "type", "distance", "denivele", "duree", "fc"}
    muscu   -> {"genre": "muscu", "type": "Musculation", "nom", "lignes": [...]}"""

    jours = {}
    if athlete_id is None:
        return jours
    conn = connexion()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, date, nom, type, distance, denivele, duree, frequence_cardiaque_moyenne "
        "FROM activites WHERE athlete_id=? AND substr(date,1,10) BETWEEN ? AND ? "
        "ORDER BY date",
        (athlete_id, debut_iso, fin_iso),
    )
    for id_, d, nom, type_, dist, dp, duree, fc in cur.fetchall():
        jours.setdefault(str(d)[:10], []).append({
            "genre": "sortie", "id": id_, "nom": nom or type_ or "Sortie",
            "type": type_ or "", "distance": dist, "denivele": dp,
            "duree": duree, "fc": fc,
        })

    try:
        cur.execute(
            "SELECT substr(date,1,10), exercice, charge_kg, series, reps_prevues, rpe, "
            "duree_min, type_seance, groupe_musculaire FROM musculation_suivi "
            "WHERE athlete_id=? AND substr(date,1,10) BETWEEN ? AND ? ORDER BY date, id",
            (athlete_id, debut_iso, fin_iso),
        )
        par_jour = {}
        for d, exo, charge, series, reps, rpe, duree_min, type_seance, groupe in cur.fetchall():
            par_jour.setdefault(d, []).append((exo, charge, series, reps, rpe, duree_min, type_seance, groupe))
        for d, lignes in par_jour.items():
            jours.setdefault(d, []).append({
                "genre": "muscu", "type": "Musculation",
                "nom": f"Musculation ({len(lignes)} exercice{'s' if len(lignes) > 1 else ''})",
                "lignes": lignes,
            })
    except Exception:
        pass
    conn.close()
    return jours


def _resume_entree(e):
    icone = ICONES_TYPE.get(e["type"], "🏃")
    if e["genre"] == "muscu":
        return f"{icone} {e['nom']}"
    morceaux = [f"{icone} {e['type'] or e['nom']}".strip()]
    if e["distance"]:
        morceaux.append(f"{e['distance']:.1f}".replace(".", ",") + " km")
    d = _formater_duree_courte(e["duree"])
    if d:
        morceaux.append(d)
    return " · ".join(morceaux)


def _texte_muscu(e):
    out = []
    for exo, charge, series, reps, rpe, duree_min, type_seance, groupe in e["lignes"]:
        parts = [str(exo)]
        if series and reps:
            parts.append(f"{series} × {reps}")
        elif series:
            parts.append(f"{series} séries")
        if charge:
            parts.append(f"{charge:g} kg")
        if rpe:
            parts.append(f"effort {rpe}/10")
        if duree_min:
            parts.append(f"{duree_min} min")
        out.append("• " + " · ".join(parts))
    return "\n".join(out)


class CalendrierActivites(QDialog):

    def __init__(self, athlete_id, parent=None, au_changement=None):
        super().__init__(parent)
        self.athlete_id = athlete_id
        self.au_changement = au_changement
        self.setWindowTitle("TrailMaster Pro – Calendrier des sorties")
        self.resize(1150, 780)

        self.mode = "Mois"
        self.jour_ref = date.today()

        acc = obtenir_couleur_accent()
        self.setStyleSheet(f"""
            QDialog, QScrollArea, #zoneCal {{ background-color: {PALETTE['fond']}; }}
            QLabel {{ color: {PALETTE['texte']}; font-family: '{POLICE_TEXTE}', sans-serif; }}
            #titrePeriode {{
                font-family: '{POLICE_TITRE}', sans-serif;
                font-size: 18px; font-weight: 700;
            }}
            #boutonNav, #boutonMode {{
                background-color: {PALETTE['carte']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 8px; padding: 6px 14px;
                color: {PALETTE['texte']};
            }}
            #boutonNav:hover, #boutonMode:hover {{
                background-color: {obtenir_couleur_accent_douce(0.18)};
            }}
            #boutonMode:checked {{
                background-color: {obtenir_couleur_accent_douce(0.30)};
                border: 1px solid {acc}; font-weight: 700;
            }}
            #enteteJour {{
                color: {PALETTE['texte_secondaire']};
                font-size: 12px; font-weight: 600;
            }}
            #celluleJour {{
                background-color: {PALETTE['carte']};
                border: 1px solid {PALETTE['bordure']};
                border-radius: 8px;
            }}
            #celluleJourAujourdhui {{
                background-color: {obtenir_couleur_accent_douce(0.16)};
                border: 1px solid {acc}; border-radius: 8px;
            }}
            #celluleRepos {{
                background-color: {PALETTE['fond_secondaire']};
                border: 1px dashed {PALETTE['bordure_douce']};
                border-radius: 8px;
            }}
            #celluleVide {{ background-color: transparent; border: none; }}
            #numeroJour {{
                font-family: '{POLICE_TEXTE_DEMI}', sans-serif; font-size: 13px;
            }}
            #detailRepos {{
                color: {PALETTE['texte_discret']}; font-size: 11px; font-style: italic;
            }}
            #detailLigne {{ color: {PALETTE['texte_secondaire']}; font-size: 11px; }}
            #resumePeriode {{ color: {PALETTE['texte_secondaire']}; font-size: 13px; }}
            #titreMiniMois {{
                background: transparent; border: none; color: {PALETTE['texte']};
                font-family: '{POLICE_TEXTE_DEMI}', sans-serif; font-size: 13px;
                text-align: left; padding: 2px 0;
            }}
            #titreMiniMois:hover {{ color: {acc}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        barre = QHBoxLayout()
        self.boutons_mode = {}
        for nom in MODES:
            b = QPushButton(nom)
            b.setObjectName("boutonMode")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=nom: self._changer_mode(n))
            self.boutons_mode[nom] = b
            barre.addWidget(b)
        barre.addSpacing(16)

        precedent = QPushButton("←")
        precedent.setObjectName("boutonNav")
        precedent.setCursor(Qt.CursorShape.PointingHandCursor)
        precedent.clicked.connect(lambda: self._decaler(-1))
        self.titre_periode = QLabel()
        self.titre_periode.setObjectName("titrePeriode")
        self.titre_periode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        suivant = QPushButton("→")
        suivant.setObjectName("boutonNav")
        suivant.setCursor(Qt.CursorShape.PointingHandCursor)
        suivant.clicked.connect(lambda: self._decaler(1))
        aujourdhui = QPushButton("Aujourd'hui")
        aujourdhui.setObjectName("boutonNav")
        aujourdhui.setCursor(Qt.CursorShape.PointingHandCursor)
        aujourdhui.clicked.connect(self._aller_aujourdhui)

        barre.addWidget(precedent)
        barre.addWidget(self.titre_periode, 1)
        barre.addWidget(suivant)
        barre.addSpacing(10)
        barre.addWidget(aujourdhui)
        layout.addLayout(barre)

        self.resume = QLabel()
        self.resume.setObjectName("resumePeriode")
        layout.addWidget(self.resume)

        note = QLabel(
            "Clique une sortie pour voir son détail. Un jour de repos (sans sortie "
            "enregistrée) se clique pour saisir une sortie oubliée ; sinon elle "
            "apparaîtra après import ou synchro Strava."
        )
        note.setObjectName("texteSecondaire")
        note.setWordWrap(True)
        layout.addWidget(note)

        defilement = QScrollArea()
        defilement.setWidgetResizable(True)
        defilement.setFrameShape(QFrame.Shape.NoFrame)
        self.zone = QWidget()
        self.zone.setObjectName("zoneCal")
        self.zone_layout = QVBoxLayout(self.zone)
        self.zone_layout.setContentsMargins(0, 0, 0, 0)
        defilement.setWidget(self.zone)
        layout.addWidget(defilement, 1)

        self._construire()

    # ---------------------------------------------------------- navigation
    def _changer_mode(self, nom):
        self.mode = nom
        self._construire()

    def _aller_aujourdhui(self):
        self.jour_ref = date.today()
        self._construire()

    def _decaler(self, sens):
        d = self.jour_ref
        if self.mode == "Semaine":
            self.jour_ref = d + timedelta(days=7 * sens)
        elif self.mode == "Mois":
            m = d.month - 1 + sens
            a = d.year + m // 12
            m = m % 12 + 1
            self.jour_ref = date(a, m, min(d.day, calendar.monthrange(a, m)[1]))
        else:
            a = d.year + sens
            self.jour_ref = date(a, d.month, min(d.day, calendar.monthrange(a, d.month)[1]))
        self._construire()

    # ---------------------------------------------------------- actions
    def _ouvrir_entree(self, e):
        if e["genre"] == "sortie":
            DialogueDetailSortie(
                e["id"], self.athlete_id, self, au_enregistrement=self._apres_changement
            ).exec()
        else:
            QMessageBox.information(self, e["nom"], _texte_muscu(e))

    def _ouvrir_nouvelle_sortie(self, jour_iso):
        DialogueNouvelleActivite(
            self.athlete_id, date_iso=jour_iso, parent=self,
            au_enregistrement=self._apres_changement,
        ).exec()

    def _clic_jour(self, jour_iso, entrees):
        """Un clic sur un jour : la sortie s'ouvre directement s'il n'y en
        a qu'une, sinon un petit menu propose de choisir ; un jour de
        repos propose de saisir une sortie."""
        if not entrees:
            self._ouvrir_nouvelle_sortie(jour_iso)
            return
        if len(entrees) == 1:
            self._ouvrir_entree(entrees[0])
            return
        menu = QMenu(self)
        for e in entrees:
            menu.addAction(_resume_entree(e), lambda e=e: self._ouvrir_entree(e))
        menu.addSeparator()
        menu.addAction("➕ Ajouter une sortie ce jour", lambda: self._ouvrir_nouvelle_sortie(jour_iso))
        menu.exec(self.cursor().pos())

    def _apres_changement(self):
        self._construire()
        if self.au_changement:
            self.au_changement()

    # ---------------------------------------------------------- construction
    def _vider(self):
        while self.zone_layout.count():
            item = self.zone_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._vider_layout(item.layout())

    def _vider_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._vider_layout(item.layout())

    def _construire(self):
        for nom, b in self.boutons_mode.items():
            b.setChecked(nom == self.mode)
        self._vider()
        if self.mode == "Semaine":
            self._vue_semaine()
        elif self.mode == "Mois":
            self._vue_mois()
        else:
            self._vue_annee()

    def _definir_resume(self, jours, debut, fin):
        today = date.today()
        sorties = [e for l in jours.values() for e in l if e["genre"] == "sortie"]
        km = sum(e["distance"] or 0 for e in sorties)
        dp = sum(e["denivele"] or 0 for e in sorties)
        sec = sum(e["duree"] or 0 for e in sorties)
        muscu = sum(1 for l in jours.values() for e in l if e["genre"] == "muscu")
        total = ((min(fin, today) - debut).days + 1) if debut <= today else 0
        actifs = len([j for j in jours if debut.isoformat() <= j <= fin.isoformat()])
        repos = max(total - actifs, 0)
        txt = (f"{len(sorties)} sortie{'s' if len(sorties) > 1 else ''} · {km:.1f} km · "
               f"D+ {dp:.0f} m · {_formater_duree_courte(sec) or '0min'} · {repos} jour{'s' if repos > 1 else ''} de repos")
        if muscu:
            txt += f" · {muscu} séance{'s' if muscu > 1 else ''} de musculation"
        self.resume.setText(txt)

    def _bouton_entree(self, e, detaille=False):
        couleur = COULEURS_TYPE.get(e["type"], COULEUR_AUTRE)
        texte = _resume_entree(e)
        if detaille and e["genre"] == "sortie":
            lignes = [texte, e["nom"]]
            plus = []
            if e["denivele"]:
                plus.append(f"D+ {e['denivele']:.0f} m")
            al = _allure_texte(e["distance"], e["duree"])
            if al:
                plus.append(al)
            if e["fc"]:
                plus.append(f"FC {e['fc']:.0f}")
            if plus:
                lignes.append(" · ".join(plus))
            texte = "\n".join(lignes)
        b = QPushButton(texte)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip("Cliquer pour voir le détail")
        b.setStyleSheet(
            f"QPushButton {{ text-align: left; background-color: {PALETTE['fond_secondaire']};"
            f" color: {PALETTE['texte']}; border: none; border-left: 4px solid {couleur};"
            f" border-radius: 4px; padding: 3px 3px 3px 5px; font-size: 10.5px; }}"
            f" QPushButton:hover {{ background-color: {obtenir_couleur_accent_douce(0.25)}; }}"
        )
        b.clicked.connect(lambda _=False, e=e: self._ouvrir_entree(e))
        return b

    def _cellule_jour(self, jour_date, entrees, detaille, hauteur):
        today = date.today()
        cellule = QFrame()
        if entrees:
            cellule.setObjectName("celluleJourAujourdhui" if jour_date == today else "celluleJour")
        elif jour_date > today:
            cellule.setObjectName("celluleVide")
        else:
            cellule.setObjectName("celluleRepos")
        cellule.setMinimumHeight(hauteur)
        # Colonnes de largeur égale, quel que soit le contenu (comme sur un vrai calendrier)
        cellule.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay = QVBoxLayout(cellule)
        lay.setContentsMargins(6, 5, 6, 5)
        lay.setSpacing(3)
        numero = QLabel(str(jour_date.day))
        numero.setObjectName("numeroJour")
        lay.addWidget(numero)
        for e in entrees:
            lay.addWidget(self._bouton_entree(e, detaille))
        if not entrees and jour_date <= today:
            repos = QPushButton("😴 repos")
            repos.setCursor(Qt.CursorShape.PointingHandCursor)
            repos.setToolTip("Cliquer pour saisir une sortie ce jour-là")
            repos.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; text-align: left;"
                f" color: {PALETTE['texte_discret']}; font-size: 11px; font-style: italic; }}"
                f" QPushButton:hover {{ color: {obtenir_couleur_accent()}; }}"
            )
            repos.clicked.connect(lambda _=False, j=jour_date.isoformat(): self._ouvrir_nouvelle_sortie(j))
            lay.addWidget(repos)
        lay.addStretch()
        return cellule

    # ---- semaine
    def _vue_semaine(self):
        lundi = _lundi(self.jour_ref)
        dimanche = lundi + timedelta(days=6)
        num = lundi.isocalendar()[1]
        self.titre_periode.setText(
            f"Semaine {num} · {lundi.day} {NOMS_MOIS[lundi.month - 1].lower()} – "
            f"{dimanche.day} {NOMS_MOIS[dimanche.month - 1].lower()} {dimanche.year}"
        )
        jours = charger_jours(self.athlete_id, lundi.isoformat(), dimanche.isoformat())
        self._definir_resume(jours, lundi, dimanche)
        grille = QGridLayout()
        grille.setSpacing(6)
        for i in range(7):
            d = lundi + timedelta(days=i)
            en_tete = QLabel(f"{NOMS_JOURS[i]} {d.day}")
            en_tete.setObjectName("enteteJour")
            en_tete.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grille.addWidget(en_tete, 0, i)
            grille.addWidget(self._cellule_jour(d, jours.get(d.isoformat(), []), True, 260), 1, i)
            grille.setColumnStretch(i, 1)
        self.zone_layout.addLayout(grille)
        self.zone_layout.addStretch()

    # ---- mois
    def _vue_mois(self):
        a, m = self.jour_ref.year, self.jour_ref.month
        self.titre_periode.setText(f"{NOMS_MOIS[m - 1]} {a}")
        premier = date(a, m, 1)
        dernier = date(a, m, calendar.monthrange(a, m)[1])
        jours = charger_jours(self.athlete_id, premier.isoformat(), dernier.isoformat())
        self._definir_resume(jours, premier, dernier)
        grille = QGridLayout()
        grille.setSpacing(6)
        for c, nom in enumerate(NOMS_JOURS):
            l = QLabel(nom)
            l.setObjectName("enteteJour")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grille.addWidget(l, 0, c)
            grille.setColumnStretch(c, 1)
        for r, semaine in enumerate(calendar.monthcalendar(a, m), start=1):
            for c, n in enumerate(semaine):
                if n == 0:
                    vide = QFrame()
                    vide.setObjectName("celluleVide")
                    vide.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                    grille.addWidget(vide, r, c)
                    continue
                d = date(a, m, n)
                grille.addWidget(self._cellule_jour(d, jours.get(d.isoformat(), []), False, 84), r, c)
        self.zone_layout.addLayout(grille)
        self.zone_layout.addStretch()

    # ---- année
    def _vue_annee(self):
        a = self.jour_ref.year
        self.titre_periode.setText(str(a))
        debut, fin = date(a, 1, 1), date(a, 12, 31)
        jours = charger_jours(self.athlete_id, debut.isoformat(), fin.isoformat())
        self._definir_resume(jours, debut, fin)
        today = date.today()

        grille = QGridLayout()
        grille.setSpacing(18)
        for m in range(1, 13):
            bloc = QVBoxLayout()
            bloc.setSpacing(4)
            titre = QPushButton(NOMS_MOIS[m - 1])
            titre.setObjectName("titreMiniMois")
            titre.setCursor(Qt.CursorShape.PointingHandCursor)
            titre.setToolTip("Afficher ce mois")
            titre.clicked.connect(lambda _=False, mm=m: self._aller_mois(a, mm))
            sorties_mois = sum(
                1 for j, l in jours.items() if j[5:7] == f"{m:02d}" for e in l if e["genre"] == "sortie"
            )
            km_mois = sum(
                (e["distance"] or 0) for j, l in jours.items() if j[5:7] == f"{m:02d}"
                for e in l if e["genre"] == "sortie"
            )
            resume = QLabel(f"{sorties_mois} sorties · {km_mois:.0f} km" if sorties_mois else "—")
            resume.setObjectName("detailLigne")
            bloc.addWidget(titre)
            bloc.addWidget(resume)

            mini = QGridLayout()
            mini.setSpacing(2)
            for c, nom in enumerate("LMMJVSD"):
                l = QLabel(nom)
                l.setObjectName("detailLigne")
                l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                mini.addWidget(l, 0, c)
            for r, semaine in enumerate(calendar.monthcalendar(a, m), start=1):
                for c, n in enumerate(semaine):
                    if n == 0:
                        continue
                    d = date(a, m, n)
                    entrees = jours.get(d.isoformat(), [])
                    mini.addWidget(self._carre_jour(d, entrees, today), r, c)
            bloc.addLayout(mini)
            bloc.addStretch()
            conteneur = QWidget()
            conteneur.setLayout(bloc)
            grille.addWidget(conteneur, (m - 1) // 4, (m - 1) % 4)
        for c in range(4):
            grille.setColumnStretch(c, 1)
        self.zone_layout.addLayout(grille)

        legende = QLabel(
            "  ".join(
                f"<span style='color:{col}'>■</span> {nom}"
                for nom, col in list(COULEURS_TYPE.items()) + [("Autre", COULEUR_AUTRE)]
            ) + "  <span style='color:#555'>■</span> Repos"
        )
        legende.setObjectName("detailLigne")
        legende.setTextFormat(Qt.TextFormat.RichText)
        self.zone_layout.addWidget(legende)
        self.zone_layout.addStretch()

    def _carre_jour(self, d, entrees, today):
        b = QPushButton(str(d.day))
        b.setFixedSize(30, 24)
        if entrees:
            # la sortie la plus longue donne la couleur du jour
            principal = max(
                entrees, key=lambda e: (e.get("distance") or 0) if e["genre"] == "sortie" else 0
            )
            couleur = COULEURS_TYPE.get(principal["type"], COULEUR_AUTRE)
            fond, texte = couleur, "#10151A"
            infos = "\n".join(_resume_entree(e) for e in entrees)
            b.setToolTip(f"{d.day:02d}/{d.month:02d}/{d.year}\n{infos}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        elif d <= today:
            fond, texte = PALETTE["fond_secondaire"], PALETTE["texte_discret"]
            b.setToolTip(f"{d.day:02d}/{d.month:02d}/{d.year} · repos")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            fond, texte = "transparent", PALETTE["texte_discret"]
        bord = f"2px solid {obtenir_couleur_accent()}" if d == today else "none"
        b.setStyleSheet(
            f"QPushButton {{ background-color: {fond}; color: {texte}; border: {bord};"
            f" border-radius: 4px; font-size: 10px; padding: 0; }}"
            f" QPushButton:hover {{ border: 2px solid {PALETTE['texte']}; }}"
        )
        if d <= today:
            b.clicked.connect(lambda _=False, j=d.isoformat(), e=entrees: self._clic_jour(j, e))
        return b

    def _aller_mois(self, annee, mois):
        self.jour_ref = date(annee, mois, 1)
        self.mode = "Mois"
        self._construire()


def ouvrir_calendrier_activites(parent, athlete_id, au_changement=None):
    dialogue = CalendrierActivites(athlete_id, parent, au_changement=au_changement)
    dialogue.exec()
