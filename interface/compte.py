from interface.conteneur_onglets import ConteneurOnglets
from interface.athletes import Athletes
from interface.reglages import Reglages
from interface.personnes import Personnes


class Compte(ConteneurOnglets):
    """Regroupe Athlètes, Réglages et Personnes (étape 2.2) dans une seule fenêtre à onglets —
    au lieu de deux fenêtres séparées, comme pour Cartes & Traces,
    Analyses & Forme, Planification, Suivi et Import & Synchro."""

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Compte",
            onglets=[
                ("👤 Athlètes", Athletes),
                ("⚙️ Réglages", Reglages),
                ("👥 Personnes", Personnes),
            ],
            athlete_id_initial=athlete_id_initial,
        )
