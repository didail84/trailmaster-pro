from interface.conteneur_onglets import ConteneurOnglets
from interface.seances import Seances
from interface.plans_entrainement import PlansEntrainement
from interface.calendrier_plan import CalendrierPlan


class Planification(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Planification",
            onglets=[
                ("📅 Plans d'entraînement", PlansEntrainement),
                ("🗓️ Calendrier (glisser-déposer)", CalendrierPlan),
                ("🏋️ Séances structurées", Seances),
            ],
            athlete_id_initial=athlete_id_initial,
        )
