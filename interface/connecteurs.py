"""
Fenêtre « 🔌 Connecteurs Claude » : ce que Claude rapporte de tes connecteurs (Strava, Garmin via Running Workout,
AllTrails, TrailSync, Google Agenda, Gmail, Spotify) et ce que tu lui demandes en retour.

  - 🔌 Pont : le dossier partagé (Google Drive) où Claude dépose chaque matin un paquet, le coureur qui le reçoit,
    l'import d'un paquet à la main, le journal des imports et le bilan de la semaine écrit par Claude ;
  - 📥 Reçu : charge de la semaine (rapport aiguë / chronique), records Strava, usure des chaussures et vélos,
    sorties reçues, agenda des 14 prochains jours (journées chargées, créneaux libres) ;
  - 🗺️ Parcours et sécurité : parcours AllTrails trouvés pour toi (favoris, lien, météo) et contrôles TrailSync
    d'un trajet (feux, fumées, alertes météo, neige) ; nouvelles recherches ;
  - ⌚ Montre, agenda, Spotify : une séance prévue envoyée sur la montre, ajoutée à l'agenda, avec sa playlist ;
    suivi de toutes les demandes faites à Claude.

Aucune requête SQL ici : noyau/donnees/connecteurs.py et noyau/connecteurs/.
Le logiciel n'appelle aucun connecteur lui-même : c'est Claude qui le fait (tâche programmée ou page Claude).
"""

import html
from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QTextBrowser,
)

from noyau.connecteurs import regles as R
from noyau.connecteurs import pont as P
from noyau.connecteurs import importer as I
from noyau.donnees import connecteurs as D
from interface.conteneur_onglets import ConteneurOnglets
from interface.forme_evolution import _EcranAthlete
from interface.calendrier_competitions import _bouton, _cadre, _table, _style_cases
from interface.organisation_logistique import DialogueChamps, _remplir, _ligne_choisie

GRIS, ORANGE, VERT, ROUGE, BLEU = "#8A949E", "#E65100", "#2E7D32", "#C62828", "#4FA3E0"
COULEUR_ZONE = {"optimal": VERT, "bas": BLEU, "eleve": ORANGE, "danger": ROUGE, "inconnu": GRIS}
COULEUR_STATUT = {"a_faire": ORANGE, "envoyee": BLEU, "fait": VERT, "erreur": ROUGE, "annulee": GRIS}
LIEN_PAGE_CLAUDE = "https://claude.ai/artifact/HJnso13N5QArSgdpKXfb9N#connecteurs"
INTERVALLE_PONT_MS = 30 * 60 * 1000


def _e(v):
    return html.escape(str(v if v is not None else ""))


def _quand(iso):
    try:
        return datetime.fromisoformat(str(iso)[:19].replace(" ", "T")).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(iso or "")


def _jour(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(iso or "")


def _km(m):
    return "" if m is None else f"{m / 1000:.1f} km".replace(".", ",")


def _ouvrir(lien):
    if lien and str(lien).startswith("https://"):
        QDesktopServices.openUrl(QUrl(lien))


class _Bus(QObject):
    change = Signal()


_BUS = _Bus()


def _apres_changement():
    _BUS.change.emit()


# ======================================================================
# Service : passage automatique du pont (au démarrage puis toutes les 30 min)
# ======================================================================

class ServicePont(QObject):
    passage_fait = Signal(str)

    def __init__(self):
        super().__init__()
        self._minuterie = QTimer(self)
        self._minuterie.setInterval(INTERVALLE_PONT_MS)
        self._minuterie.timeout.connect(self.lancer)
        self.dernier_texte = ""

    def demarrer(self, delai_ms=12000):
        QTimer.singleShot(delai_ms, self.lancer)
        self._minuterie.start()

    def lancer(self):
        if not P.dossier():
            return None
        try:
            res = P.passage()
        except Exception as e:          # un dossier réseau absent ne doit rien bloquer
            self.dernier_texte = f"⚠️ Pont indisponible : {e}"
            self.passage_fait.emit(self.dernier_texte)
            return None
        self.dernier_texte = P.texte_passage(res)
        if res["importes"] or res.get("demandes") is not None:
            _apres_changement()
        self.passage_fait.emit(self.dernier_texte)
        return res


_service = None


def service():
    global _service
    if _service is None:
        _service = ServicePont()
    return _service


# ======================================================================
# Squelette d'onglet
# ======================================================================

class _EcranConnecteurs(_EcranAthlete):

    def __init__(self, titre, sous_titre, athlete_id_initial=None):
        super().__init__(titre, sous_titre, athlete_id_initial or P.athlete_du_pont())
        _BUS.change.connect(self._changement)

    def _finir(self):
        self._finaliser()
        _style_cases(self)

    def actualiser(self, *_):
        self.rafraichir()

    def _changement(self):
        try:
            self.rafraichir()
        except RuntimeError:
            pass

    def showEvent(self, ev):
        super().showEvent(ev)
        if getattr(self, "_vu", False):
            self.actualiser()
        self._vu = True

    def _athlete_ou_message(self):
        a = self.athlete_id
        if a is None:
            QMessageBox.information(self, "Coureur", "Choisis d'abord le coureur en haut de l'écran.")
        return a

    def _erreur(self, e):
        QMessageBox.warning(self, "Connecteurs Claude", str(e))


# ======================================================================
# 🔌 Pont
# ======================================================================

class PontEcran(_EcranConnecteurs):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🔌  Pont avec Claude",
                         "Chaque matin, Claude interroge tes connecteurs (Strava, Garmin, AllTrails, TrailSync, Google "
                         "Agenda, Gmail, Spotify) et dépose un paquet dans le dossier Google Drive « "
                         f"{P.NOM_DOSSIER_DRIVE} ». Le logiciel le lit tout seul (au démarrage puis toutes les 30 min), "
                         "sans doublon, et y laisse tes demandes (séance pour la montre, agenda, playlist…).",
                         athlete_id_initial)
        cadre, lc = _cadre("Dossier partagé")
        h = QHBoxLayout()
        self.chemin = QLineEdit()
        self.chemin.setPlaceholderText(f"…/Mon Drive/{P.NOM_DOSSIER_DRIVE}")
        self.chemin.setReadOnly(True)
        b_choisir = _bouton("Choisir le dossier…")
        b_choisir.clicked.connect(self._choisir)
        self.proposes = QComboBox()
        self.proposes.addItem("Dossiers Google Drive trouvés…", None)
        for d in P.dossiers_probables():
            self.proposes.addItem(str(d), str(d))
        self.proposes.activated.connect(self._propose)
        h.addWidget(self.chemin, 1)
        h.addWidget(b_choisir)
        h.addWidget(self.proposes)
        lc.addLayout(h)
        b = QHBoxLayout()
        self.b_lire = _bouton("Lire le dossier maintenant", True)
        self.b_lire.clicked.connect(self._lire)
        b_imp = _bouton("Importer un paquet…")
        b_imp.clicked.connect(self._importer)
        b_page = _bouton("Ouvrir la page Claude ↗")
        b_page.clicked.connect(lambda: _ouvrir(LIEN_PAGE_CLAUDE))
        for w in (self.b_lire, b_imp, b_page):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.etat = QLabel("")
        self.etat.setWordWrap(True)
        self.etat.setObjectName("texteSecondaire")
        lc.addWidget(self.etat)
        aide = QLabel(
            "Pas de Google Drive sur cet ordinateur ? Télécharge le paquet depuis drive.google.com (ou depuis la page "
            "Claude, rubrique Connecteurs) et utilise « Importer un paquet… ». Les demandes, elles, ne partent qu'avec "
            "un dossier partagé.")
        aide.setWordWrap(True)
        aide.setObjectName("texteSecondaire")
        lc.addWidget(aide)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Bilan de la semaine (écrit par Claude)")
        self.bilan = QTextBrowser()
        self.bilan.setOpenExternalLinks(True)
        self.bilan.setMinimumHeight(130)
        lc.addWidget(self.bilan)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Paquets importés")
        self.table = _table(["Reçu le", "Fichier", "Créé par Claude le", "Ce qui est arrivé"], 240)
        lc.addWidget(self.table)
        self.principal.addWidget(cadre, 1)
        service().passage_fait.connect(lambda t: self._etat_texte(t))
        self._finir()

    def _etat_texte(self, texte=None):
        try:
            d = P.dossier()
            dp = P.dernier_passage()
            entete = (f"Dernier passage : {_quand(dp)}. " if dp else "") if d else "Aucun dossier choisi. "
            self.etat.setText(entete + (texte or service().dernier_texte or ""))
        except RuntimeError:
            pass

    def rafraichir(self):
        d = P.dossier()
        self.chemin.setText(str(d) if d else "")
        self.b_lire.setEnabled(d is not None)
        if self.athlete_id is not None and self.athlete_id != P.athlete_du_pont():
            P.definir_athlete(self.athlete_id)
        self._etat_texte()
        b = D.bilan_semaine()
        self.bilan.setHtml(
            f"<p style='color:{GRIS}'>Reçu le {_e(_quand(b['date']))}</p><p>{_e(b['texte']).replace(chr(10), '<br>')}</p>"
            if b else f"<p style='color:{GRIS}'>Le bilan arrive avec le paquet du lundi matin.</p>")
        j = I.journal()
        _remplir(self.table, [(_quand(x["importe_le"]), x["fichier"] or "", _quand(x["cree_le"]), x["resume"]) for x in j])

    def _choisir(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier partagé avec Claude", str(P.dossier() or ""))
        if d:
            self._definir(d)

    def _propose(self, _i):
        d = self.proposes.currentData()
        if d:
            self._definir(d)

    def _definir(self, d):
        try:
            P.definir_dossier(d)
        except R.ErreurConnecteurs as e:
            return self._erreur(e)
        self._lire()

    def _lire(self):
        if self._athlete_ou_message() is None:
            return
        P.definir_athlete(self.athlete_id)
        service().lancer()
        self.rafraichir()

    def _importer(self):
        a = self._athlete_ou_message()
        if a is None:
            return
        f, _ = QFileDialog.getOpenFileName(self, "Paquet des connecteurs", "", "Paquet Trail Hub Center (*.json)")
        if not f:
            return
        try:
            b = P.importer_fichier(f, a)
        except (R.ErreurConnecteurs, ValueError) as e:
            return self._erreur(e)
        QMessageBox.information(self, "Paquet importé",
                                "Ce paquet était déjà importé." if b.get("deja") else R.resume_paquet(b))
        _apres_changement()


# ======================================================================
# 📥 Reçu des connecteurs
# ======================================================================

class RecuEcran(_EcranConnecteurs):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📥  Reçu des connecteurs",
                         "Charge de la semaine calculée par Running Workout (Garmin), records et matériel de Strava, "
                         "sorties reçues, et ton agenda des 14 prochains jours : une journée très prise compte dans "
                         "la fatigue (diagnostic du matin et analyses de l'IA).",
                         athlete_id_initial)
        h = QHBoxLayout()
        self.c_charge = self._carte("Charge 7 j / 42 j")
        self.c_chaussure = self._carte("Chaussures")
        self.c_agenda = self._carte("Agenda de demain")
        for c in (self.c_charge, self.c_chaussure, self.c_agenda):
            h.addWidget(c, 1)
        self.principal.addLayout(h)

        cadre, lc = _cadre("Records (Strava)")
        self.t_records = _table(["Sport", "Record", "Temps / valeur", "Date"], 180)
        lc.addWidget(self.t_records)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Matériel suivi par Strava")
        self.t_mat = _table(["Matériel", "Type", "Kilomètres", "Usure", "État", "Statut"], 140)
        lc.addWidget(self.t_mat)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Sorties reçues par les connecteurs")
        self.t_sorties = _table(["Date", "Sortie", "Type", "Distance", "D+", "Durée", "Source"], 200)
        lc.addWidget(self.t_sorties)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Agenda des 14 prochains jours")
        self.t_agenda = _table(["Jour", "Heures prises", "Fatigue", "Créneaux libres pour courir"], 260)
        lc.addWidget(self.t_agenda)
        self.principal.addWidget(cadre, 1)
        self._finir()

    def rafraichir(self):
        a = self.athlete_id
        if a is None:
            for t in (self.t_records, self.t_mat, self.t_sorties, self.t_agenda):
                t.setRowCount(0)
            return
        c = D.derniere_charge(a)
        if c:
            coul = COULEUR_ZONE.get(c["zone"], GRIS)
            self.c_charge.valeur.setText(f"{c['acwr']:.2f}".replace(".", ","))
            self.c_charge.valeur.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {coul};")
            self.c_charge.detail.setText(f"<b style='color:{coul}'>{_e(c['libelle'])}</b> (zone conseillée 0,8 à 1,3). "
                                         f"{_e(c['conseil'])}<br><span style='color:{GRIS}'>{_e(c['source'])}, "
                                         f"{_e(_jour(c['date']))}</span>")
        else:
            self.c_charge.valeur.setText("—")
            self.c_charge.detail.setText("Arrive avec le premier paquet.")
        mats = D.materiel_strava(a)
        chauss = [m for m in mats if m["type"] == "Chaussures" and m["statut"] == "Actif"]
        if chauss:
            m = max(chauss, key=lambda x: x["km"])
            self.c_chaussure.valeur.setText(f"{m['km']:.0f} km")
            self.c_chaussure.detail.setText(f"{_e(m['nom'])} : {_e(m['usure']['etat'])}, encore ~{m['usure']['reste_km']} km "
                                            f"(repère {R.USURE_CHAUSSURE_KM} km).")
        else:
            self.c_chaussure.valeur.setText("—")
            self.c_chaussure.detail.setText("Aucune chaussure reçue de Strava.")
        fat = D.fatigue_par_jour(a, jours=14)
        demain = fat[1] if len(fat) > 1 else None
        if demain:
            self.c_agenda.valeur.setText(f"{demain['heures']:g} h".replace(".", ","))
            self.c_agenda.detail.setText(("Journée chargée : séance facile conseillée." if demain["chargee"] else
                                          "Journée normale.")
                                         + (" Libre : " + ", ".join(f"{d}–{f}" for d, f in demain["creneaux"][:3])
                                            if demain["creneaux"] else ""))
        rec = D.records(a)
        _remplir(self.t_records, [(r["sport"], r["libelle"], r["texte"], _jour(r["date"])) for r in rec])
        coul = {}
        lignes = []
        for i, m in enumerate(mats):
            u = m["usure"]
            if u:
                coul[(i, 4)] = ROUGE if u["pct"] >= 100 else ORANGE if u["pct"] >= 85 else VERT
            lignes.append((m["nom"], m["type"], f"{m['km']:.0f} km", f"{u['pct']} %" if u else "",
                           u["etat"] if u else "", m["statut"]))
        _remplir(self.t_mat, lignes, coul)
        _remplir(self.t_sorties, [(_quand(s["date"]), s["nom"], s["type"], f"{s['distance'] or 0:.1f} km".replace(".", ","),
                                   f"{s['denivele'] or 0} m", f"{(s['duree'] or 0) // 60} min", s["source"])
                                  for s in D.activites_recues(a)])
        coul = {}
        for i, f in enumerate(fat):
            if f["bonus"]:
                coul[(i, 2)] = ROUGE if f["bonus"] >= 2 else ORANGE
        _remplir(self.t_agenda, [(_jour(f["jour"]), f"{f['heures']:g} h".replace(".", ","),
                                  ("Journée très chargée" if f["bonus"] >= 2 else "Journée chargée") if f["bonus"] else "Normale",
                                  ", ".join(f"{d}–{fi}" for d, fi in f["creneaux"])) for f in fat], coul)


# ======================================================================
# 🗺️ Parcours et sécurité
# ======================================================================

class ParcoursSecuriteEcran(_EcranConnecteurs):

    def __init__(self, athlete_id_initial=None):
        super().__init__("🗺️  Parcours et sécurité",
                         "Parcours de trail trouvés sur AllTrails (distance, dénivelé, difficulté, météo au départ), et "
                         "contrôles TrailSync d'un trajet en voiture (feux, fumées, alertes météo, neige et gel). "
                         "Tes recherches partent à Claude au prochain passage du pont.",
                         athlete_id_initial)
        cadre, lc = _cadre("Parcours (AllTrails)")
        self.t_parcours = _table(["★", "Parcours", "Lieu", "Distance", "D+", "Difficulté", "Note", "Reçu le"], 260)
        self.t_parcours.doubleClicked.connect(lambda _i: self._ouvrir_parcours())
        self.t_parcours.itemSelectionChanged.connect(self._detail)
        lc.addWidget(self.t_parcours)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("texteSecondaire")
        lc.addWidget(self.detail)
        b = QHBoxLayout()
        b1 = _bouton("Chercher des parcours…", True)
        b1.clicked.connect(self._chercher)
        b2 = _bouton("★ Favori")
        b2.clicked.connect(self._favori)
        b3 = _bouton("Ouvrir sur AllTrails ↗")
        b3.clicked.connect(self._ouvrir_parcours)
        for w in (b1, b2, b3):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre, 1)

        cadre, lc = _cadre("Sécurité des trajets (TrailSync)")
        self.t_secu = _table(["Date", "Trajet", "Niveau", "Résumé"], 180)
        self.t_secu.doubleClicked.connect(lambda _i: self._ouvrir_secu())
        lc.addWidget(self.t_secu)
        b = QHBoxLayout()
        b1 = _bouton("Contrôler un trajet…", True)
        b1.clicked.connect(self._securite)
        b.addWidget(b1)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)
        self._finir()

    def rafraichir(self):
        a = self.athlete_id
        self._parcours = D.parcours(a) if a else []
        self._secu = D.securite(a) if a else []
        _remplir(self.t_parcours, [("★" if p["favori"] else "", p["nom"], p["lieu"] or "", _km(p["distance_m"]),
                                    f"{p['denivele_m']:.0f} m" if p["denivele_m"] is not None else "",
                                    p["difficulte"] or "", f"{p['note']:.1f}".replace(".", ",") if p["note"] else "",
                                    _jour(p["recu_le"])) for p in self._parcours])
        coul = {}
        for i, s in enumerate(self._secu):
            n = (s["niveau"] or "").lower()
            coul[(i, 2)] = ROUGE if n in ("danger", "alerte", "rouge") else ORANGE if n in ("vigilance", "orange") else VERT
        _remplir(self.t_secu, [(_jour(s["date"]), s["trajet"], s["niveau"] or "", s["resume"] or "") for s in self._secu], coul)
        self._detail()

    def _choisi(self):
        return _ligne_choisie(self.t_parcours, self._parcours)

    def _detail(self):
        p = self._choisi()
        self.detail.setText(f"Météo au départ : {p['meteo']}" if p and p.get("meteo") else "")

    def _ouvrir_parcours(self):
        p = self._choisi()
        if p:
            _ouvrir(p["lien"])

    def _ouvrir_secu(self):
        s = _ligne_choisie(self.t_secu, self._secu)
        if s:
            if s.get("lien"):
                _ouvrir(s["lien"])
            elif s.get("details"):
                QMessageBox.information(self, s["trajet"], s["details"])

    def _favori(self):
        p = self._choisi()
        if p:
            D.basculer_favori(p["id"])
            self.rafraichir()

    def _chercher(self):
        a = self._athlete_ou_message()
        if a is None:
            return
        spec = [("texte", "lieu", "Autour de", {"aide": "L'Isle-sur-la-Sorgue"}),
                ("reel", "lat", "Latitude", {"decimales": 4, "max": 90}),
                ("reel", "lon", "Longitude", {"decimales": 4, "max": 180}),
                ("entier", "rayon", "Rayon (km)", {"min": 1, "max": 200, "defaut": 20}),
                ("entier", "distance", "Distance voulue (km, 0 = peu importe)", {"max": 200}),
                ("entier", "denivele", "Dénivelé voulu (m, 0 = peu importe)", {"max": 10000})]
        dlg = DialogueChamps(self, "Chercher des parcours de trail", spec,
                             {"lieu": "L'Isle-sur-la-Sorgue", "lat": 43.9194, "lon": 5.0511, "rayon": 20},
                             enregistrer=lambda c: D.demander_parcours(
                                 a, c["lieu"] or "ma position", c["lat"], c["lon"], c["distance"] or None,
                                 c["denivele"] or None, c["rayon"]))
        if dlg.exec():
            self._apres_demande()

    def _securite(self):
        a = self._athlete_ou_message()
        if a is None:
            return
        spec = [("texte", "depart", "Départ", {"aide": "L'Isle-sur-la-Sorgue"}),
                ("texte", "arrivee", "Arrivée", {"aide": "Chalet Reynard, Mont Ventoux"}),
                ("date", "jour", "Le", None)]

        def ok(c):
            if not c["depart"] or not c["arrivee"]:
                raise R.ErreurConnecteurs("Indique le départ et l'arrivée.")
            return D.demander_securite(a, c["depart"], c["arrivee"], c["jour"])
        dlg = DialogueChamps(self, "Contrôler un trajet", spec, {"depart": "L'Isle-sur-la-Sorgue",
                                                                  "jour": date.today().isoformat()}, enregistrer=ok)
        if dlg.exec():
            self._apres_demande()

    def _apres_demande(self):
        n = P.ecrire_demandes() if P.dossier() else None
        QMessageBox.information(self, "Demande prête",
                                "La demande est déposée pour Claude : le résultat arrivera avec le prochain paquet."
                                if n is not None else
                                "La demande est enregistrée. Choisis le dossier partagé (onglet Pont) pour qu'elle "
                                "parte à Claude.")
        _apres_changement()


# ======================================================================
# ⌚ Montre, agenda, Spotify
# ======================================================================

class DemandesEcran(_EcranConnecteurs):

    def __init__(self, athlete_id_initial=None):
        super().__init__("⌚  Montre, agenda et Spotify",
                         "Choisis une séance prévue : Claude l'envoie sur ta Fenix (Running Workout : 4 séances par "
                         "mois en compte gratuit), la place dans Google Agenda sur un créneau libre, et te prépare "
                         "une playlist Spotify de la bonne durée (funk et disco 80-90 par défaut).",
                         athlete_id_initial)
        cadre, lc = _cadre("Séances prévues")
        self.t_seances = _table(["Date", "Séance", "Type", "Durée", "Étapes"], 220)
        lc.addWidget(self.t_seances)
        b = QHBoxLayout()
        b1 = _bouton("⌚ Envoyer sur la montre", True)
        b1.clicked.connect(self._montre)
        b2 = _bouton("📅 Ajouter à l'agenda")
        b2.clicked.connect(self._agenda)
        b3 = _bouton("🎵 Créer la playlist")
        b3.clicked.connect(self._playlist)
        b4 = _bouton("Les trois d'un coup")
        b4.clicked.connect(self._tout)
        for w in (b1, b2, b3, b4):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre)

        cadre, lc = _cadre("Demandes faites à Claude")
        self.t_dem = _table(["Créée le", "Demande", "Type", "Statut", "Réponse"], 240)
        self.t_dem.doubleClicked.connect(lambda _i: self._ouvrir_demande())
        lc.addWidget(self.t_dem)
        b = QHBoxLayout()
        b1 = _bouton("Annuler la demande")
        b1.clicked.connect(self._annuler)
        b2 = _bouton("Ouvrir le résultat ↗")
        b2.clicked.connect(self._ouvrir_demande)
        for w in (b1, b2):
            b.addWidget(w)
        b.addStretch()
        lc.addLayout(b)
        self.principal.addWidget(cadre, 1)

        cadre, lc = _cadre("Playlists Spotify")
        self.t_play = _table(["Playlist", "Séance", "Durée", "Créée le"], 140)
        self.t_play.doubleClicked.connect(lambda _i: self._ouvrir_playlist())
        lc.addWidget(self.t_play)
        self.principal.addWidget(cadre)
        self._finir()

    def rafraichir(self):
        a = self.athlete_id
        self._seances = D.seances_prevues(a) if a else []
        _remplir(self.t_seances, [(_jour(s["date_prevue"]), s["nom"], s["type_seance"] or "",
                                   f"{s['duree_min']} min" if s["duree_min"] else "", str(len(s["etapes"])))
                                  for s in self._seances])
        self._demandes = D.demandes()
        _remplir(self.t_dem, [(_quand(d["cree_le"]), d["titre"], d["type_libelle"], d["statut_libelle"],
                               d["message"] or (d["lien"] or "")) for d in self._demandes],
                 {(i, 3): COULEUR_STATUT.get(d["statut"], GRIS) for i, d in enumerate(self._demandes)})
        self._playlists = D.playlists(a) if a else []
        _remplir(self.t_play, [(p["nom"], p["seance"] or "", f"{p['duree_min']} min" if p["duree_min"] else "",
                                _jour(p["cree_le"])) for p in self._playlists])

    def _seance(self):
        s = _ligne_choisie(self.t_seances, self._seances)
        if s is None:
            QMessageBox.information(self, "Séance", "Choisis une séance prévue dans la liste.")
        return s

    def _montre(self, silencieux=False):
        s, a = self._seance(), self.athlete_id
        if s is None or a is None:
            return False
        try:
            D.demander_seance_montre(a, s)
        except R.ErreurConnecteurs as e:
            self._erreur(e)
            return False
        return silencieux or self._apres_demande()

    def _agenda(self, silencieux=False):
        s, a = self._seance(), self.athlete_id
        if s is None or a is None:
            return False
        jour = (s.get("date_prevue") or date.today().isoformat())[:10]
        libres = []
        for f in D.fatigue_par_jour(a, jour, 1):
            libres = f["creneaux"]
        proposee = libres[-1][0] if libres else "18:00"
        heure, ok = QInputDialog.getText(self, "Heure de la séance",
                                         "Heure de départ (HH:MM)" + (f" — libre : {', '.join(f'{d}–{fi}' for d, fi in libres)}"
                                                                      if libres else ""), text=proposee)
        if not ok:
            return False
        try:
            debut = datetime.fromisoformat(f"{jour}T{heure.strip()}")
        except ValueError:
            self._erreur("Heure illisible : écris par exemple 18:30.")
            return False
        fin = debut + timedelta(minutes=max(20, s["duree_min"] or 60))
        try:
            D.demander_agenda(a, f"🏃 {s['nom']}", debut.isoformat(), fin.isoformat(),
                              description=f"Séance prévue dans Trail Hub Center ({s.get('type_seance') or 'course'}).")
        except R.ErreurConnecteurs as e:
            self._erreur(e)
            return False
        return silencieux or self._apres_demande()

    def _playlist(self, silencieux=False):
        s, a = self._seance(), self.athlete_id
        if s is None or a is None:
            return False
        D.demander_playlist(a, s["nom"], s["duree_min"] or 45)
        return silencieux or self._apres_demande()

    def _tout(self):
        if self._seance() is None:
            return
        if self._montre(True) and self._agenda(True) and self._playlist(True):
            self._apres_demande()

    def _apres_demande(self):
        n = P.ecrire_demandes() if P.dossier() else None
        QMessageBox.information(self, "Demande prête",
                                "C'est déposé pour Claude : ce sera fait au prochain passage (chaque matin, ou tout de "
                                "suite depuis la page Claude)." if n is not None else
                                "Demande enregistrée. Choisis le dossier partagé (onglet Pont) pour qu'elle parte à Claude.")
        _apres_changement()
        return True

    def _annuler(self):
        d = _ligne_choisie(self.t_dem, self._demandes)
        if d and d["statut"] in ("a_faire", "envoyee"):
            D.annuler_demande(d["cle"])
            if P.dossier():
                P.ecrire_demandes()
            _apres_changement()

    def _ouvrir_demande(self):
        d = _ligne_choisie(self.t_dem, self._demandes)
        if d:
            _ouvrir(d.get("lien"))

    def _ouvrir_playlist(self):
        p = _ligne_choisie(self.t_play, self._playlists)
        if p:
            _ouvrir(p.get("lien"))


class ConnecteursFenetre(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(titre="Connecteurs Claude", onglets=[("🔌 Pont", PontEcran), ("📥 Reçu", RecuEcran),
                                                               ("🗺️ Parcours et sécurité", ParcoursSecuriteEcran),
                                                               ("⌚ Montre, agenda, Spotify", DemandesEcran)],
                         athlete_id_initial=athlete_id_initial)
        self.pont, self.recu, self.parcours, self.demandes = self.ecrans
