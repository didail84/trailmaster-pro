from interface.conteneur_onglets import ConteneurOnglets
from interface.athletes import Athletes
from interface.reglages import Reglages


class Compte(ConteneurOnglets):
    """Regroupe Athlètes et Réglages dans une seule fenêtre à onglets —
    au lieu de deux fenêtres séparées, comme pour Cartes & Traces,
    Analyses & Forme, Planification, Suivi et Import & Synchro."""

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Compte",
            onglets=[
                ("👤 Athlètes", Athletes),
                ("⚙️ Réglages", Reglages),
            ],
            athlete_id_initial=athlete_id_initial,
        )
