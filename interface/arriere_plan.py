"""
Calculs en arrière-plan (U3) : l'interface ne se fige plus pendant qu'un
écran prépare ses chiffres.

    executer(fonction, rappel, *args, proprietaire=widget)

`fonction` tourne dans un fil de travail (jamais de widget dedans : que
des calculs et des lectures de base), puis `rappel(resultat, erreur)`
est appelé dans le fil de l'interface. Si `proprietaire` a été détruit
entre-temps (écran fermé), le rappel est ignoré. Un petit cache mémoire
évite de refaire un calcul identique pendant quelques minutes.
"""

import itertools
import queue
import time

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer
try:
    from shiboken6 import isValid
except ImportError:  # pragma: no cover
    def isValid(_o):
        return True

_compteur = itertools.count(1)
_rappels = {}
_cache = {}
_taches = {}   # références Python gardées jusqu'à la livraison (évite tout ramasse-miettes prématuré)


class _Relais(QObject):
    """Relève, dans le fil de l'interface, les résultats déposés par les
    fils de travail (file thread-safe + minuteur : fiable quelle que soit
    la plateforme, contrairement à un signal inter-fils)."""

    def __init__(self):
        super().__init__()
        self.file = queue.Queue()
        self.minuteur = QTimer(self)
        self.minuteur.setInterval(25)
        self.minuteur.timeout.connect(self._relever)

    def demarrer(self):
        if not self.minuteur.isActive():
            self.minuteur.start()

    def _relever(self):
        while True:
            try:
                jeton, resultat, erreur = self.file.get_nowait()
            except queue.Empty:
                break
            self._livrer(jeton, resultat, erreur)
        if not _rappels:
            self.minuteur.stop()

    def _livrer(self, jeton, resultat, erreur):
        _taches.pop(jeton, None)
        entree = _rappels.pop(jeton, None)
        if entree is None:
            return
        rappel, proprietaire, cle, ttl = entree
        if cle is not None and erreur is None:
            _cache[cle] = (time.time() + ttl, resultat)
        if proprietaire is not None:
            try:
                if not isValid(proprietaire):
                    return
            except Exception:
                return
        try:
            rappel(resultat, erreur)
        except RuntimeError:
            pass  # widget détruit entre-temps


_relais = None


def _obtenir_relais():
    global _relais
    if _relais is None:
        _relais = _Relais()  # créé dans le fil de l'interface (premier appel)
    return _relais


class _Tache(QRunnable):
    def __init__(self, jeton, fonction, args, relais):
        super().__init__()
        self.jeton, self.fonction, self.args, self.relais = jeton, fonction, args, relais

    def run(self):
        try:
            resultat, erreur = self.fonction(*self.args), None
        except Exception as e:  # noqa: BLE001 — remonté au rappel
            resultat, erreur = None, e
        self.relais.file.put((self.jeton, resultat, erreur))


def executer(fonction, rappel, *args, proprietaire=None, cle_cache=None, ttl=300):
    """Lance `fonction(*args)` en arrière-plan. `cle_cache` : hashable
    qui identifie le calcul (None = pas de cache)."""
    relais = _obtenir_relais()
    if cle_cache is not None:
        trouve = _cache.get(cle_cache)
        if trouve and trouve[0] > time.time():
            rappel(trouve[1], None)
            return
    jeton = next(_compteur)
    _rappels[jeton] = (rappel, proprietaire, cle_cache, ttl)
    tache = _Tache(jeton, fonction, args, relais)
    tache.setAutoDelete(False)
    _taches[jeton] = tache
    relais.demarrer()
    QThreadPool.globalInstance().start(tache)


def vider_cache():
    _cache.clear()
