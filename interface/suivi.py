from interface.conteneur_onglets import ConteneurOnglets
from interface.blessures import Blessures
from interface.soins import Soins
from interface.materiel import Materiel
from interface.nutrition import Nutrition
from interface.zones_entrainement import ZonesEntrainement
from interface.objectifs import Objectifs
from interface.poids_fatigue import PoidsFatigue
from interface.sante_charge import PoidsLisse
from interface.carte_corps import CarteCorps


class Suivi(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Suivi",
            onglets=[
                ("⚖️ Poids & fatigue", PoidsFatigue),
                ("📉 Poids lissé", PoidsLisse),
                ("🩹 Blessures", Blessures),
                ("🧍 Carte du corps", CarteCorps),
                ("💆 Soins", Soins),
                ("🎒 Matériel", Materiel),
                ("🥗 Nutrition", Nutrition),
                ("📈 Zones d'entraînement", ZonesEntrainement),
                ("🎯 Objectifs", Objectifs),
            ],
            athlete_id_initial=athlete_id_initial,
        )
