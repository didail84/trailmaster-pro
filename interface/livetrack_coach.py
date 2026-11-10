"""
Fenêtre « 📡 LiveTrack coach » : suivre en direct, avec le lien Garmin LiveTrack, la sortie de ses coureurs.

  - 📡 Suivi en direct : choisir un coureur, coller le lien reçu (le message entier convient), le suivre ; la page
    LiveTrack s'affiche dans la fenêtre (ou dans le navigateur) ; plusieurs coureurs à la fois, un clic pour passer de
    l'un à l'autre ; terminer, annuler, reprendre ;
  - 🗂️ Historique : tous les suivis, la sortie reçue ensuite de la montre rattachée au suivi (elle reçoit alors son
    analyse toute seule), séance prévue, notes, export / import de sauvegarde, effacement des vieux liens ;
  - ✉️ Message et test : le message à envoyer au coureur pour qu'il lance LiveTrack, et le test de configuration de
    5 minutes (ce que le coach voit vraiment : carte, allure, fréquence cardiaque).

Ce que le logiciel ne fait PAS : lire les données de la page LiveTrack (Garmin n'en donne pas l'accès). La page
s'affiche telle quelle ; la fréquence cardiaque n'y est visible que si Garmin l'affiche (le test le dit).
Aucune requête SQL ici : noyau/donnees/livetrack.py. Le réseau n'est utilisé que par la page affichée.
"""

import html
import os
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QSplitter,
    QTextBrowser, QVBoxLayout, QWidget,
)

from noyau.donnees import livetrack as dliv
from noyau.livetrack import regles as R
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import DialogueChamps, _remplir, _ligne_choisie

GRIS, ORANGE, VERT, ROUGE = "#8A949E", "#E65100", "#2E7D32", "#C62828"
COULEUR_ETAT = {"en_cours": VERT, "termine": GRIS, "annule": GRIS, "expire": ORANGE}
ENV_SANS_VUE_WEB = "TRAILHUB_SANS_VUE_WEB"        # tests : pas de moteur web (inutile et lourd hors écran)


def _e(v):
    return html.escape(str(v if v is not None else ""))


def _quand(iso):
    try:
        return datetime.fromisoformat(str(iso)[:19]).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(iso or "")


class _Bus(QObject):
    """Prévient tous les onglets quand une donnée a changé (un seul rafraîchissement, sans lien entre onglets)."""
    change = Signal()


_BUS = _Bus()


def _apres_changement():
    _BUS.change.emit()


class _EcranLive(_EcranAthlete):
    """Squelette d'un onglet : la barre « Athlète » n'a pas de sens ici (les coureurs sont ceux du coach)."""

    def __init__(self, titre, sous_titre, athlete_id_initial=None):
        super().__init__(titre, sous_titre, athlete_id_initial)
        for i in range(self.barre.count()):
            w = self.barre.itemAt(i).widget()
            if w is not None:
                w.hide()
        _BUS.change.connect(self._changement)

    def _finir(self):
        self._finaliser()
        _style_cases(self)

    def actualiser(self, *_):
        self.rafraichir()

    def _changement(self):
        try:
            self.rafraichir()
        except RuntimeError:                  # écran déjà détruit côté Qt
            pass

    def showEvent(self, ev):
        super().showEvent(ev)
        if getattr(self, "_vu", False):
            self.actualiser()
        self._vu = True

    def _erreur(self, e):
        if isinstance(e, R.ErreurLiveTrack):
            QMessageBox.warning(self, "LiveTrack coach", str(e))
        else:
            raise e


def _combo_coureurs(combo, avec_tous=False, garder=True):
    """Remplit la liste des coureurs en gardant le choix courant."""
    actuel = combo.currentData() if garder else None
    combo.blockSignals(True)
    combo.clear()
    if avec_tous:
        combo.addItem("Tous les coureurs", None)
    liste = dliv.coureurs()
    for c in liste:
        combo.addItem(c["nom"], c["id"])
    i = combo.findData(actuel)
    combo.setCurrentIndex(max(0, i))
    combo.blockSignals(False)
    return liste


def _spec_coureur():
    profils = [(None, "Aucun (coureur qui n'a pas de profil ici)")] + dliv.athletes_disponibles()
    return [("texte", "nom", "Nom du coureur", {"aide": "Prénom Nom"}),
            ("choix", "athlete_id", "Profil dans le logiciel", {"choix": profils, "defaut": None}),
            ("texte", "montre", "Montre", {"aide": "Fenix 6 Pro, Forerunner 945…"}),
            ("texte", "objectif", "Objectif", {"aide": "UTMB 2027, sortie longue du dimanche…"}),
            ("long", "notes", "Notes", {"hauteur": 80})]


def dialogue_coureur(parent, coureur=None):
    """Fiche d'un coureur (création si `coureur` est None). Renvoie l'id, ou None si annulé."""
    def enregistrer(champs):
        if coureur:
            dliv.modifier_coureur(coureur["id"], champs)
            return coureur["id"]
        return dliv.creer_coureur(champs)
    d = DialogueChamps(parent, "Modifier le coureur" if coureur else "Nouveau coureur", _spec_coureur(), coureur,
                       enregistrer)
    return d.resultat if d.exec() else None


# ======================================================================
# Page LiveTrack affichée dans la fenêtre
# ======================================================================

class VueLive(QWidget):
    """La page LiveTrack du coureur choisi : intégrée si le moteur web est là, sinon un bouton vers le navigateur."""

    def __init__(self):
        super().__init__()
        self.lien = None
        self.web = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info.setStyleSheet(f"color:{GRIS}; font-size:14px;")
        lay.addWidget(self.info, 1)
        if not os.environ.get(ENV_SANS_VUE_WEB):
            try:
                from PySide6.QtWebEngineWidgets import QWebEngineView
                self.web = QWebEngineView()
                self.web.setMinimumHeight(380)
                lay.addWidget(self.web, 4)
                self.web.hide()
            except Exception:                                    # moteur web absent : le bouton du navigateur suffit
                self.web = None
        self.afficher(None)

    @property
    def integree(self):
        return self.web is not None

    def afficher(self, lien, message=None):
        self.lien = lien or None
        if not self.lien:
            self.info.setText(message or "Choisis un suivi dans la liste : sa page LiveTrack s'affichera ici.")
            self.info.show()
            if self.web is not None:
                self.web.hide()
                self.web.setUrl(QUrl("about:blank"))
            return
        if self.web is None:
            self.info.setText("La page ne peut pas s'afficher dans la fenêtre sur cet ordinateur.\n"
                              "Utilise « Ouvrir dans le navigateur ».")
            self.info.show()
            return
        self.info.hide()
        self.web.show()
        self.web.setUrl(QUrl(self.lien))

    def recharger(self):
        if self.web is not None and self.lien:
            self.web.reload()

    def ouvrir_navigateur(self):
        if self.lien:
            QDesktopServices.openUrl(QUrl(self.lien))


# ======================================================================
# Onglet 1 — suivi en direct
# ======================================================================

class SuiviEnDirect(_EcranLive):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📡  Suivi en direct (LiveTrack)",
                         "Colle le lien LiveTrack que le coureur t'envoie : sa page s'affiche ici. "
                         "Plusieurs coureurs en même temps, un clic pour passer de l'un à l'autre. "
                         "Le logiciel ne lit pas les données de la page : il l'affiche, c'est tout.", athlete_id_initial)
        self._liste = []
        cadre, lc = _cadre("Nouveau suivi")
        h = QHBoxLayout()
        self.coureur = QComboBox()
        self.coureur.setMinimumWidth(220)
        h.addWidget(QLabel("Coureur :"))
        h.addWidget(self.coureur)
        b_nouveau, b_modif = _bouton("➕ Nouveau coureur"), _bouton("✏️ Modifier")
        b_nouveau.clicked.connect(self._nouveau_coureur)
        b_modif.clicked.connect(self._modifier_coureur)
        h.addWidget(b_nouveau)
        h.addWidget(b_modif)
        h.addStretch()
        lc.addLayout(h)
        h2 = QHBoxLayout()
        self.lien = QLineEdit()
        self.lien.setPlaceholderText("Colle ici le lien (https://livetrack.garmin.com/…) ou le message entier du coureur")
        self.lien.returnPressed.connect(self._suivre)
        self.b_suivre = _bouton("▶ Suivre ce lien", True)
        self.b_suivre.clicked.connect(self._suivre)
        b_coller = _bouton("📋 Coller")
        b_coller.clicked.connect(self._coller)
        h2.addWidget(self.lien, 1)
        h2.addWidget(b_coller)
        h2.addWidget(self.b_suivre)
        lc.addLayout(h2)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setStyleSheet(f"color:{GRIS};")
        lc.addWidget(self.message)
        self.principal.addWidget(cadre)

        cadre2, l2 = _cadre("En direct")
        sp = QSplitter(Qt.Orientation.Horizontal)
        gauche = QWidget()
        lg = QVBoxLayout(gauche)
        lg.setContentsMargins(0, 0, 0, 0)
        self.table = _table(["Coureur", "Depuis", "Durée", "État", "FC sur la page"], 300)
        self.table.itemSelectionChanged.connect(self._selection)
        lg.addWidget(self.table, 1)
        sp.addWidget(gauche)
        droite = QWidget()
        ld = QVBoxLayout(droite)
        ld.setContentsMargins(0, 0, 0, 0)
        self.vue = VueLive()
        ld.addWidget(self.vue, 1)
        sp.addWidget(droite)
        sp.setSizes([480, 700])
        l2.addWidget(sp, 1)
        b = QHBoxLayout()
        self.boutons = {}
        for code, texte, principal, fonction in (
                ("nav", "🌐 Ouvrir dans le navigateur", True, self._navigateur),
                ("rech", "🔄 Recharger", False, self.vue.recharger),
                ("copier", "📋 Copier le lien", False, self._copier),
                ("fin", "✔ Sortie terminée", False, self._terminer),
                ("reprise", "↩ Reprendre", False, self._reprendre),
                ("annule", "✖ Annuler", False, self._annuler)):
            w = _bouton(texte, principal)
            w.clicked.connect(fonction)
            self.boutons[code] = w
            b.addWidget(w)
        b.addWidget(QLabel("FC vue sur la page :"))
        self.fc = QComboBox()
        for lib, v in (("pas vérifié", None), ("oui", 1), ("non", 0)):
            self.fc.addItem(lib, v)
        self.fc.activated.connect(self._definir_fc)
        b.addWidget(self.fc)
        b.addStretch()
        l2.addLayout(b)
        self.principal.addWidget(cadre2, 1)
        self.minuteur = QTimer(self)
        self.minuteur.setInterval(30_000)                    # les durées et les « expiré probable » se mettent à jour
        self.minuteur.timeout.connect(self._tic)
        self._finir()

    # -- affichage
    def rafraichir(self):
        _combo_coureurs(self.coureur)
        choisi = self._choisi()
        self._liste = dliv.suivis(etats=("en_cours", "expire"))
        lignes, couleurs = [], {}
        for r, s in enumerate(self._liste):
            lignes.append((s["coureur_nom"], _quand(s["debut"]), R.duree_texte(s["duree"]), s["etat_libelle"],
                           R.LIBELLE_FC[s["fc_visible"]] if s["fc_visible"] is not None else "—"))
            couleurs[(r, 3)] = COULEUR_ETAT.get(s["etat_code"])
        _remplir(self.table, lignes, couleurs)
        if choisi:
            for r, s in enumerate(self._liste):
                if s["id"] == choisi["id"]:
                    self.table.selectRow(r)
                    break
        elif self._liste:
            self.table.selectRow(0)
        self._selection()
        if not self._liste:
            self.message.setText("Aucun suivi en cours. Colle un lien pour commencer.")

    def _tic(self):
        if self.isVisible():
            self.rafraichir()

    def showEvent(self, ev):
        super().showEvent(ev)
        self.minuteur.start()

    def hideEvent(self, ev):
        self.minuteur.stop()
        super().hideEvent(ev)

    def _choisi(self):
        return _ligne_choisie(self.table, self._liste)

    def _selection(self):
        s = self._choisi()
        self.vue.afficher(s["lien"] if s else None,
                          None if s else "Choisis un suivi dans la liste : sa page LiveTrack s'affichera ici.")
        for code in ("nav", "rech", "copier"):
            self.boutons[code].setEnabled(bool(s and s["lien"]))
        self.boutons["fin"].setEnabled(bool(s))
        self.boutons["annule"].setEnabled(bool(s))
        self.boutons["reprise"].setEnabled(False)           # un suivi repris se fait depuis l'historique
        self.fc.setEnabled(bool(s))
        if s:
            self.fc.setCurrentIndex(max(0, self.fc.findData(s["fc_visible"])))
        if s:
            self.message.setText(f"{s['coureur_nom']} — {s['etat_libelle'].lower()} depuis {_quand(s['debut'])}.")

    # -- actions
    def _nouveau_coureur(self):
        cid = dialogue_coureur(self)
        if cid:
            _apres_changement()
            self.coureur.setCurrentIndex(max(0, self.coureur.findData(cid)))

    def _modifier_coureur(self):
        cid = self.coureur.currentData()
        c = dliv.coureur(cid) if cid else None
        if c is None:
            QMessageBox.information(self, "LiveTrack coach", "Ajoute d'abord un coureur.")
            return
        if dialogue_coureur(self, c):
            _apres_changement()

    def _coller(self):
        t = QGuiApplication.clipboard().text()
        if t:
            self.lien.setText(t)

    def _suivre(self):
        cid = self.coureur.currentData()
        if not cid:
            QMessageBox.information(self, "LiveTrack coach", "Ajoute d'abord un coureur (bouton « Nouveau coureur »).")
            return
        try:
            sid = dliv.ajouter_suivi(cid, self.lien.text())
        except Exception as e:
            self._erreur(e)
            return
        self.lien.clear()
        _apres_changement()
        for r, s in enumerate(self._liste):
            if s["id"] == sid:
                self.table.selectRow(r)
                break

    def _navigateur(self):
        self.vue.ouvrir_navigateur()

    def _copier(self):
        s = self._choisi()
        if s and s["lien"]:
            QGuiApplication.clipboard().setText(s["lien"])
            self.message.setText("Lien copié.")

    def _terminer(self):
        s = self._choisi()
        if s:
            dliv.terminer_suivi(s["id"])
            _apres_changement()

    def _annuler(self):
        s = self._choisi()
        if s and QMessageBox.question(self, "LiveTrack coach", f"Annuler le suivi de {s['coureur_nom']} ?") \
                == QMessageBox.StandardButton.Yes:
            dliv.annuler_suivi(s["id"])
            _apres_changement()

    def _reprendre(self):
        s = self._choisi()
        if s:
            try:
                dliv.reprendre_suivi(s["id"])
            except Exception as e:
                self._erreur(e)
                return
            _apres_changement()

    def _definir_fc(self, _i):
        s = self._choisi()
        if s:
            dliv.definir_fc_visible(s["id"], self.fc.currentData())
            _apres_changement()


# ======================================================================
# Onglet 2 — historique
# ======================================================================

def _html_suivi(s, analyse):
    if not s:
        return "<p style='color:#8A949E'>Choisis un suivi.</p>"
    if s["activite_id"]:
        km = f"{(s['sortie_km'] or 0):.1f}".replace(".", ",")
        duree = f" en {R.duree_texte(s['sortie_duree'])}" if s["sortie_duree"] else ""
        sortie = f"<p>🏃 Sortie rattachée : <b>{_e(s['sortie_nom'] or 'Sortie')}</b> — {km} km{duree}</p>"
    else:
        sortie = ("<p style='color:#8A949E'>Aucune sortie rattachée. Quand la montre a envoyé la sortie (Garmin Connect "
                  "ou Strava), rattache-la : elle sera analysée toute seule.</p>")
    if s["activite_id"]:
        ana = (f"<h4 style='margin:10px 0 2px 0'>Analyse de la sortie</h4>{_markdown_simple(analyse)}" if analyse else
               "<p style='color:#8A949E'>L'analyse s'écrit toute seule dès que la sortie est prête.</p>")
    else:
        ana = ""
    return (f"<h3 style='margin:0 0 4px 0'>{_e(s['coureur_nom'])}</h3>"
            f"<p style='color:#8A949E;margin:0 0 8px 0'>{_e(_quand(s['debut']))} · {_e(s['etat_libelle'])}"
            + (f" · {_e(R.duree_texte(s['duree']))}" if s["duree"] else "") + "</p>"
            f"<p>FC sur la page : {_e(R.LIBELLE_FC[s['fc_visible']])}</p>{sortie}"
            + (f"<p>📝 {_e(s['notes'])}</p>" if s["notes"] else "") + ana)


def _markdown_simple(texte):
    """Texte d'analyse (un peu de markdown) → HTML sûr : titres, gras et retours à la ligne seulement."""
    lignes = []
    for l in html.escape(texte or "").splitlines():
        if l.startswith("#"):
            lignes.append(f"<p><b>{l.lstrip('# ').strip()}</b></p>")
        elif l.strip():
            lignes.append(f"<p style='margin:2px 0'>{l.replace('**', '')}</p>")
    return "".join(lignes)


class HistoriqueSuivis(_EcranLive):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🗂️  Historique des suivis",
                         "Tous les suivis LiveTrack. Rattache la sortie envoyée ensuite par la montre : elle reçoit "
                         "son analyse automatiquement. Le lien lui-même est effacé 30 jours après la fin du suivi.",
                         athlete_id_initial)
        self._liste = []
        h = QHBoxLayout()
        self.filtre = QComboBox()
        h.addWidget(QLabel("Coureur :"))
        h.addWidget(self.filtre)
        h.addStretch()
        b_exp, b_imp, b_purge = _bouton("📤 Exporter une sauvegarde"), _bouton("📥 Importer une sauvegarde"), \
            _bouton("🧹 Effacer les vieux liens")
        b_exp.clicked.connect(self._exporter)
        b_imp.clicked.connect(self._importer)
        b_purge.clicked.connect(self._purger)
        for w in (b_exp, b_imp, b_purge):
            h.addWidget(w)
        self.principal.addLayout(h)
        cadre, lc = _cadre("Suivis")
        sp = QSplitter(Qt.Orientation.Horizontal)
        self.table = _table(["Date", "Coureur", "Durée", "État", "Sortie", "FC page"], 420)
        self.table.itemSelectionChanged.connect(self._detail)
        sp.addWidget(self.table)
        self.fiche = QTextBrowser()
        self.fiche.setMinimumWidth(380)
        sp.addWidget(self.fiche)
        sp.setSizes([620, 560])
        lc.addWidget(sp, 1)
        b = QHBoxLayout()
        self.boutons = {}
        for code, texte, principal, fonction in (
                ("rattacher", "🔗 Rattacher la sortie…", True, self._rattacher),
                ("detacher", "Détacher la sortie", False, self._detacher),
                ("seance", "🗓️ Séance prévue…", False, self._seance),
                ("notes", "📝 Notes…", False, self._notes),
                ("reprendre", "↩ Reprendre", False, self._reprendre),
                ("supprimer", "🗑️ Supprimer", False, self._supprimer)):
            w = _bouton(texte, principal)
            w.clicked.connect(fonction)
            self.boutons[code] = w
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre, 1)
        self.filtre.currentIndexChanged.connect(lambda _i: self.rafraichir(garder_filtre=True))
        try:                                                  # une analyse arrive : la fiche se met à jour
            from interface.analyse_auto import service
            service().analyse_prete.connect(lambda *_: self._detail() if self.isVisible() else None)
        except Exception:
            pass
        self._finir()

    def rafraichir(self, garder_filtre=False):
        _combo_coureurs(self.filtre, avec_tous=True)
        choisi = self._choisi()
        self._liste = dliv.suivis(coureur_id=self.filtre.currentData())
        lignes, couleurs = [], {}
        for r, s in enumerate(self._liste):
            lignes.append((_quand(s["debut"]), s["coureur_nom"], R.duree_texte(s["duree"]), s["etat_libelle"],
                           ("🏃 " + (s["sortie_nom"] or "rattachée")) if s["activite_id"] else "",
                           {1: "oui", 0: "non"}.get(s["fc_visible"], "")))
            couleurs[(r, 3)] = COULEUR_ETAT.get(s["etat_code"])
        _remplir(self.table, lignes, couleurs)
        if choisi:
            for r, s in enumerate(self._liste):
                if s["id"] == choisi["id"]:
                    self.table.selectRow(r)
                    break
        self._detail()

    def _choisi(self):
        return _ligne_choisie(self.table, self._liste)

    def _detail(self):
        s = self._choisi()
        self.fiche.setHtml(_html_suivi(s, dliv.analyse_de_la_sortie(s["id"]) if s else None))
        for code, w in self.boutons.items():
            w.setEnabled(s is not None)
        if s:
            self.boutons["detacher"].setEnabled(bool(s["activite_id"]))
            self.boutons["rattacher"].setEnabled(True)
            self.boutons["reprendre"].setEnabled(s["etat"] in ("termine", "annule") and bool(s["lien"]))

    def _rattacher(self):
        s = self._choisi()
        if not s:
            return
        if not s["athlete_id"]:
            QMessageBox.information(self, "LiveTrack coach", "Ce coureur n'a pas de profil dans le logiciel : "
                                    "relie sa fiche à un profil (bouton « Modifier » de l'onglet Suivi en direct) pour "
                                    "retrouver ses sorties.")
            return
        cand = dliv.activites_candidates(s["id"])
        if not cand:
            QMessageBox.information(self, "LiveTrack coach",
                                    "Aucune sortie de ce coureur autour de ce suivi. Synchronise la montre "
                                    "(Import & Synchro) puis réessaie.")
            return
        noms = [f"{_quand(a['date'])} · {a['nom'] or a['type'] or 'Sortie'} · {(a['distance'] or 0):.1f} km".replace(".", ",")
                for a in cand]
        nom, ok = QInputDialog.getItem(self, "Rattacher la sortie", "Quelle sortie correspond à ce suivi ?", noms, 0, False)
        if ok:
            try:
                dliv.rattacher_activite(s["id"], cand[noms.index(nom)]["id"])
            except Exception as e:
                self._erreur(e)
                return
            _apres_changement()

    def _detacher(self):
        s = self._choisi()
        if s:
            dliv.detacher_activite(s["id"])
            _apres_changement()

    def _seance(self):
        s = self._choisi()
        if not s:
            return
        prevues = dliv.seances_prevues(s["athlete_id"], datetime.fromisoformat(s["debut"]))
        if not prevues:
            QMessageBox.information(self, "LiveTrack coach", "Pas de séance prévue autour de ce jour pour ce coureur "
                                    "(il faut un profil relié et un plan dans Planification).")
            return
        noms = ["(aucune)"] + [f"{p['date_prevue']} · {p['nom']}" for p in prevues]
        nom, ok = QInputDialog.getItem(self, "Séance prévue", "Séance que le coureur devait faire :", noms, 0, False)
        if ok:
            i = noms.index(nom)
            dliv.choisir_seance(s["id"], prevues[i - 1]["id"] if i else None)
            _apres_changement()

    def _notes(self):
        s = self._choisi()
        if not s:
            return
        t, ok = QInputDialog.getMultiLineText(self, "Notes du coach", "Ce que tu as vu pendant le suivi :", s["notes"] or "")
        if ok:
            dliv.noter_suivi(s["id"], t)
            _apres_changement()

    def _reprendre(self):
        s = self._choisi()
        if s:
            try:
                dliv.reprendre_suivi(s["id"])
            except Exception as e:
                self._erreur(e)
                return
            _apres_changement()

    def _supprimer(self):
        s = self._choisi()
        if s and QMessageBox.question(self, "LiveTrack coach", "Supprimer ce suivi de l'historique ? "
                                      "(la sortie de la montre, elle, reste dans le logiciel)") \
                == QMessageBox.StandardButton.Yes:
            dliv.supprimer_suivi(s["id"])
            _apres_changement()

    def _purger(self):
        n = dliv.nb_liens_a_purger()
        if not n:
            QMessageBox.information(self, "LiveTrack coach", "Aucun lien à effacer : ils le sont tout seuls "
                                    f"{dliv.DUREE_LIEN_APRES_FIN_JOURS} jours après la fin du suivi.")
            return
        if QMessageBox.question(self, "LiveTrack coach", f"Effacer {n} lien(s) de suivis terminés ? L'historique reste.") \
                == QMessageBox.StandardButton.Yes:
            dliv.purger_liens()
            _apres_changement()

    def _exporter(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter les suivis", "livetrack-coach.json", "JSON (*.json)")
        if chemin:
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(dliv.exporter_json())
            QMessageBox.information(self, "LiveTrack coach", "Sauvegarde enregistrée.")

    def _importer(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Importer une sauvegarde", "", "JSON (*.json)")
        if not chemin:
            return
        try:
            with open(chemin, encoding="utf-8") as f:
                n = dliv.importer(f.read())
        except Exception as e:
            self._erreur(e)
            return
        QMessageBox.information(self, "LiveTrack coach", f"Ajoutés : {n['coureurs']} coureur(s), {n['suivis']} suivi(s), "
                                f"{n['tests']} test(s). Rien n'a été écrasé.")
        _apres_changement()


# ======================================================================
# Onglet 3 — message au coureur et test de configuration
# ======================================================================

class MessageEtTest(_EcranLive):

    def __init__(self, athlete_id_initial=None):
        super().__init__("✉️  Message au coureur et test",
                         "Le message qui explique au coureur comment lancer LiveTrack, et le test de 5 minutes à faire "
                         "avec lui avant le jour J : ce que tu vois vraiment sur la page (carte, allure, fréquence "
                         "cardiaque).", athlete_id_initial)
        self._tests = []
        self._message_auto = ""                  # le dernier message écrit par le logiciel (pour savoir s'il a été retouché)
        h = QHBoxLayout()
        self.coureur = QComboBox()
        self.coureur.setMinimumWidth(220)
        h.addWidget(QLabel("Coureur :"))
        h.addWidget(self.coureur)
        h.addStretch()
        self.principal.addLayout(h)

        cadre, lc = _cadre("Message à envoyer au coureur")
        self.texte = QPlainTextEdit()
        self.texte.setMinimumHeight(260)
        lc.addWidget(self.texte)
        b = QHBoxLayout()
        b_copier, b_refaire = _bouton("📋 Copier le message", True), _bouton("↺ Refaire le message")
        b_copier.clicked.connect(self._copier)
        b_refaire.clicked.connect(self._refaire)
        b.addWidget(b_copier)
        b.addWidget(b_refaire)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)

        cadre2, l2 = _cadre("Test de configuration (5 minutes)")
        self.choix = {}
        for code, libelle in R.POINTS_TEST:
            ligne = QHBoxLayout()
            ligne.addWidget(QLabel(libelle), 1)
            c = QComboBox()
            for lib, v in (("— pas vérifié", None), ("oui", True), ("non", False)):
                c.addItem(lib, v)
            self.choix[code] = c
            ligne.addWidget(c)
            l2.addLayout(ligne)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Note (facultatif) : ce qu'il faut redemander au coureur…")
        l2.addWidget(self.note)
        self.bilan = QLabel("")
        self.bilan.setWordWrap(True)
        self.bilan.setStyleSheet("font-weight:600;")
        l2.addWidget(self.bilan)
        b_test = _bouton("✔ Enregistrer le test", True)
        b_test.clicked.connect(self._enregistrer_test)
        l2.addWidget(b_test, 0, Qt.AlignmentFlag.AlignLeft)
        self.historique = _table(["Date", "Bilan"], 150)
        l2.addWidget(self.historique)
        self.principal.addWidget(cadre2)
        self.principal.addStretch(1)
        self.coureur.currentIndexChanged.connect(lambda _i: self._changer_coureur())
        self._finir()

    def rafraichir(self):
        _combo_coureurs(self.coureur)
        self._changer_coureur(garder_texte=True)

    def _changer_coureur(self, garder_texte=False):
        cid = self.coureur.currentData()
        c = dliv.coureur(cid) if cid else None
        actuel = self.texte.toPlainText().strip()
        if not garder_texte or not actuel or actuel == self._message_auto:      # pas modifié à la main : on le refait
            self._refaire()
        self._tests = dliv.tests(cid) if cid else []
        _remplir(self.historique, [(_quand(t["fait_le"]), t["bilan"]) for t in self._tests])
        t = self._tests[0] if self._tests else None
        for code, combo in self.choix.items():
            combo.setCurrentIndex(max(0, combo.findData((t["resultats"] or {}).get(code))) if t else 0)
        self.bilan.setText(t["bilan"] if t else "")
        self.bilan.setEnabled(c is not None)

    def _refaire(self):
        cid = self.coureur.currentData()
        c = dliv.coureur(cid) if cid else None
        prenom = (c["nom"].split()[0] if c and c["nom"] else "")
        self._message_auto = R.modele_message(prenom, "", (c or {}).get("montre") or "", (c or {}).get("objectif") or "")
        self.texte.setPlainText(self._message_auto)

    def _copier(self):
        QGuiApplication.clipboard().setText(self.texte.toPlainText())
        self.bilan.setText("Message copié : colle-le dans ta messagerie.")

    def _resultats(self):
        return {code: combo.currentData() for code, combo in self.choix.items()}

    def _enregistrer_test(self):
        cid = self.coureur.currentData()
        if not cid:
            QMessageBox.information(self, "LiveTrack coach", "Ajoute d'abord un coureur (onglet Suivi en direct).")
            return
        try:
            _tid, bilan = dliv.enregistrer_test(cid, self._resultats(), self.note.text())
        except Exception as e:
            self._erreur(e)
            return
        self.note.clear()
        _apres_changement()
        self.bilan.setText(bilan)


# ======================================================================
# Fenêtre
# ======================================================================

class LiveTrackCoachFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        try:
            dliv.purger_liens()                  # les liens des vieux suivis n'ont plus d'utilité : effacés sans bruit
        except Exception:
            pass
        super().__init__(titre="LiveTrack coach",
                         onglets=[("📡 Suivi en direct", SuiviEnDirect), ("🗂️ Historique", HistoriqueSuivis),
                                  ("✉️ Message et test", MessageEtTest)],
                         athlete_id_initial=athlete_id_initial)
        self.direct, self.historique, self.message = self.ecrans
