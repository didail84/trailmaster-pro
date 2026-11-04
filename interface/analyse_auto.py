"""
Service d'analyses automatiques, côté interface.

Écoute l'événement « donnees_modifiees » (import, synchro, saisie d'une
sortie…) et lance en arrière-plan un passage de noyau/ia/analyse_auto :
les nouvelles sorties reçoivent leur analyse sans clic. Un passage a
aussi lieu peu après le démarrage du logiciel.

Les écrans qui affichent des analyses (fil d'activité, fiche sortie)
se branchent sur le signal `analyse_prete(activite_id, source)` pour se
mettre à jour dès qu'une analyse arrive.
"""

import time

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from noyau.outils.evenements import abonner, DONNEES_MODIFIEES

PAUSE_APRES_ECHEC_IA_S = 15 * 60     # si l'IA a échoué (quota, réseau), on ne la relance pas avant 15 min


class _Passage(QThread):
    une_analyse = Signal(int, str)

    def __init__(self, essayer_ia, parent=None):
        super().__init__(parent)
        self.essayer_ia = essayer_ia
        self.echec_ia = False

    def run(self):
        from noyau.ia import analyse_auto as aa
        if not aa.actif():
            return
        essayer = self.essayer_ia
        for activite_id, athlete_id in aa.sorties_a_analyser():
            try:
                _texte, source = aa.analyser(activite_id, athlete_id, essayer)
            except Exception:
                continue
            if source == "local" and essayer and aa._ia_disponible():
                essayer, self.echec_ia = False, True
            if source != "absente":
                self.une_analyse.emit(activite_id, source)


class ServiceAnalysesAuto(QObject):
    analyse_prete = Signal(int, str)
    _demande = Signal()

    def __init__(self):
        super().__init__()
        self._fil = None
        self._en_attente = False
        self._dernier_echec_ia = 0.0
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(2500)          # regroupe les imports en rafale
        self._minuterie.timeout.connect(self._lancer)
        self._demande.connect(self._minuterie.start)  # signal : l'événement peut venir d'un autre fil
        abonner(DONNEES_MODIFIEES, self._sur_modification)

    def _sur_modification(self, **_):
        self._demande.emit()

    def demarrer(self, delai_ms=8000):
        QTimer.singleShot(delai_ms, self._lancer)

    def relancer(self):
        self._demande.emit()

    def _lancer(self):
        if self._fil is not None and self._fil.isRunning():
            self._en_attente = True
            return
        essayer_ia = time.monotonic() - self._dernier_echec_ia > PAUSE_APRES_ECHEC_IA_S or not self._dernier_echec_ia
        self._fil = _Passage(essayer_ia, self)
        self._fil.une_analyse.connect(self.analyse_prete)
        self._fil.finished.connect(self._fini)
        self._fil.start()

    def _fini(self):
        if self._fil is not None and self._fil.echec_ia:
            self._dernier_echec_ia = time.monotonic()
        if self._en_attente:
            self._en_attente = False
            self._minuterie.start()


_service = None


def service():
    """Le service unique du logiciel (créé au premier appel)."""
    global _service
    if _service is None:
        _service = ServiceAnalysesAuto()
    return _service
