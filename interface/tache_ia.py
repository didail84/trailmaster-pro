"""
Petit utilitaire partagé par les écrans qui déclenchent une analyse IA
(détail de sortie, historique, bilans périodiques) : exécute l'appel
réseau (potentiellement lent — plusieurs tentatives de secours avant
d'échouer) dans un thread séparé, pour que la fenêtre reste réactive
pendant l'attente au lieu de se figer plusieurs dizaines de secondes.
"""

from PySide6.QtCore import QThread, Signal


class TacheAnalyseIA(QThread):
    """Exécute `fonction_analyse` (un callable sans argument, en général
    une petite lambda enveloppant analyser_sortie(...)/analyser_periode(...))
    dans un thread à part. Émet reussite(résultat) si tout se passe bien
    (résultat = exactement ce que renvoie fonction_analyse — un tuple à
    2 ou 4 éléments selon l'appelant, jamais décomposé ici), ou
    echec(message) si une ErreurAnalyseIA (ou une erreur inattendue) est
    levée."""

    reussite = Signal(object)
    echec = Signal(str)

    def __init__(self, fonction_analyse, parent=None):
        super().__init__(parent)
        self._fonction_analyse = fonction_analyse

    def run(self):
        from interface.ia_coach import ErreurAnalyseIA
        try:
            resultat = self._fonction_analyse()
        except ErreurAnalyseIA as erreur:
            self.echec.emit(str(erreur))
        except Exception as erreur:
            self.echec.emit(f"Erreur inattendue : {erreur}")
        else:
            self.reussite.emit(resultat)
