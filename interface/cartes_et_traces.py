from interface.conteneur_onglets import ConteneurOnglets
from interface.secteurs import Secteurs
from interface.segments import Segments
from interface.carte_thermique_ecran import CarteThermiqueEcran
from interface.carte_reelle import CarteReelle
from interface.createur_parcours import CreateurParcours
from interface.liste_parcours import ListeParcours


class CartesEtTraces(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Cartes & Traces",
            onglets=[
                ("📍 Mes parcours", ListeParcours),
                ("🖊️ Créer un parcours", CreateurParcours),
                ("🧭 Secteurs", Secteurs),
                ("🎯 Segments précis", Segments),
                ("🔥 Carte thermique", CarteThermiqueEcran),
                ("🗺️ Carte réelle", CarteReelle),
            ],
            athlete_id_initial=athlete_id_initial,
        )
