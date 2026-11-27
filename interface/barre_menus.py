"""
Mini-fenêtre dans la barre des menus (Mac) ou la zone de notification
(Windows) : le score « Prêt à courir » du jour, la prochaine séance, et
un bouton pour l'envoyer sur la montre, sans ouvrir le logiciel.

Aussi : deux services lancés avec la fenêtre principale —
  - le rapport du mois en PDF, écrit tout seul le 1er du mois ;
  - le thème « Selon le soleil », qui bascule au lever et au coucher.
"""

from datetime import date, datetime

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from data.database import obtenir_parametre, definir_parametre

CLE_ACTIVE = "barre_menus_active"
INTERVALLE_MS = 30 * 60 * 1000


def active():
    return obtenir_parametre(CLE_ACTIVE, "1") == "1"


def definir_active(oui):
    definir_parametre(CLE_ACTIVE, "1" if oui else "0")


def contenu(athlete_id):
    """Ce qu'affiche la mini-fenêtre : {score, verdict, conseil, seance}."""
    res = {"score": None, "verdict": "", "conseil": "", "seance": None}
    if athlete_id is None:
        return res
    try:
        from noyau.sante.pret_a_courir import calculer
        p = calculer(athlete_id)
        res.update(score=p["score"], verdict=p["verdict"], conseil=p["conseil"])
    except Exception:
        pass
    try:
        from noyau.donnees.connecteurs import seances_prevues
        res["seance"] = next(iter(seances_prevues(athlete_id)), None)
    except Exception:
        pass
    return res


class BarreMenus(QObject):

    def __init__(self, fenetre, icone):
        super().__init__(fenetre)
        self.fenetre = fenetre
        self.tray = QSystemTrayIcon(icone, fenetre)
        self.menu = QMenu()
        self.a_score = QAction("Prêt à courir : —", self.menu)
        self.a_score.setEnabled(False)
        self.a_conseil = QAction("", self.menu)
        self.a_conseil.setEnabled(False)
        self.a_seance = QAction("Prochaine séance : —", self.menu)
        self.a_seance.setEnabled(False)
        self.a_montre = QAction("Envoyer la séance sur la montre", self.menu)
        self.a_montre.triggered.connect(self._montre)
        a_ouvrir = QAction("Ouvrir Trail Master Hub Pro", self.menu)
        a_ouvrir.triggered.connect(self._ouvrir)
        for a in (self.a_score, self.a_conseil, self.a_seance):
            self.menu.addAction(a)
        self.menu.addSeparator()
        self.menu.addAction(self.a_montre)
        self.menu.addAction(a_ouvrir)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda raison: self._ouvrir() if raison == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self._seance = None
        self._minuterie = QTimer(self)
        self._minuterie.setInterval(INTERVALLE_MS)
        self._minuterie.timeout.connect(self.actualiser)

    def demarrer(self):
        if not QSystemTrayIcon.isSystemTrayAvailable() or not active():
            return False
        self.tray.show()
        self.actualiser()
        self._minuterie.start()
        return True

    def arreter(self):
        self._minuterie.stop()
        self.tray.hide()

    def actualiser(self):
        c = contenu(getattr(self.fenetre, "athlete_actif_id", None))
        self.a_score.setText(f"Prêt à courir : {c['score']}/100 — {c['verdict']}" if c["score"] is not None
                             else "Prêt à courir : pas encore de données")
        self.a_conseil.setText(c["conseil"][:80])
        s = c["seance"]
        self._seance = s
        if s:
            j = s.get("date_prevue") or ""
            quand = "aujourd'hui" if j[:10] == date.today().isoformat() else j[:10]
            self.a_seance.setText(f"Prochaine séance : {s['nom']} ({quand}, {s['duree_min']} min)")
        else:
            self.a_seance.setText("Prochaine séance : aucune de prévue")
        self.a_montre.setEnabled(bool(s and s.get("etapes")))
        self.tray.setToolTip(f"Trail Master Hub Pro — {c['score']}/100" if c["score"] is not None else "Trail Master Hub Pro")

    def _montre(self):
        s = self._seance
        if not s:
            return
        try:
            from noyau.donnees.connecteurs import demander_seance_montre
            from noyau.connecteurs import pont as P
            demander_seance_montre(self.fenetre.athlete_actif_id, s)
            envoye = P.ecrire_demandes() if P.dossier() else None
            self.tray.showMessage("Séance pour la montre",
                                  f"« {s['nom']} » part au prochain passage de Claude." if envoye is not None else
                                  "Demande enregistrée : choisis le dossier partagé dans Connecteurs Claude.")
        except Exception as e:
            self.tray.showMessage("Séance pour la montre", str(e))

    def _ouvrir(self):
        self.fenetre.showNormal()
        self.fenetre.raise_()
        self.fenetre.activateWindow()


class ServicesFond(QObject):
    """Rapport du mois automatique et bascule du thème « Selon le soleil »."""

    def __init__(self, fenetre, notifier=None):
        super().__init__(fenetre)
        self.fenetre = fenetre
        self.notifier = notifier or (lambda titre, texte: None)
        self._theme = QTimer(self)
        self._theme.setSingleShot(True)
        self._theme.timeout.connect(self._bascule_theme)

    def demarrer(self):
        QTimer.singleShot(20000, self.rapport_du_mois)
        self._programmer_theme()

    def rapport_du_mois(self, aujourdhui=None):
        from noyau.outils import rapport_auto as R
        mois = R.mois_a_ecrire(aujourdhui)
        aid = getattr(self.fenetre, "athlete_actif_id", None)
        if not mois or aid is None:
            return None
        an, mo = mois
        try:
            from interface.rapport_pdf import construire_rapport, ecrire_pdf
            from data.database import obtenir_athletes
            nom = next((f"{a[2]} {a[1]}" for a in obtenir_athletes() if a[0] == aid), "coureur")
            d = R.dossier()
            d.mkdir(parents=True, exist_ok=True)
            chemin = d / R.nom_fichier(nom, an, mo)
            html, images = construire_rapport(aid, "mois", date(an, mo, 1))
            ecrire_pdf(html, images, str(chemin))
        except Exception as e:
            self.notifier("Rapport du mois", f"Le rapport n'a pas pu être écrit : {e}")
            return None
        R.marquer_ecrit(an, mo)
        self.notifier("Rapport du mois", f"Le rapport de {mo:02d}/{an} est prêt : {chemin}")
        return chemin

    def _programmer_theme(self):
        from interface.theme import obtenir_mode_couleur, lieu_soleil
        if obtenir_mode_couleur() != "Soleil":
            return
        from noyau.outils.soleil import prochain_changement
        lat, lon = lieu_soleil()
        ms = int(max(60, (prochain_changement(None, lat, lon) - datetime.now()).total_seconds() + 30) * 1000)
        self._theme.start(min(ms, 6 * 3600 * 1000))

    def _bascule_theme(self):
        from interface.theme import palette_a_jour, definir_mode_couleur, obtenir_mode_couleur, mode_effectif
        if obtenir_mode_couleur() == "Soleil" and not palette_a_jour():
            definir_mode_couleur("Soleil")
            self.notifier("Thème", "Mode nuit : il s'applique aux écrans que tu ouvres maintenant (redémarre le logiciel "
                          "pour tout passer en mode nuit)." if mode_effectif() == "Sombre" else
                          "Mode jour : il s'applique aux écrans que tu ouvres maintenant.")
        self._programmer_theme()
