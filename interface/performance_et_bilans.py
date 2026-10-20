from interface.conteneur_onglets import ConteneurOnglets
from interface.performance_traces import (
    MonteesVAM, AllureAjustee, ResistanceFatigue, EfficaciteCourse, TerrainPente, MeteoPerformance, FormeDistance,
)
from interface.bilans_objectifs import TotauxPeriodes, ComparerPeriodes, ObjectifsAnnuels, PlanifierCharge
from interface.partage_images import AfficheAnnuelle
from interface.rapport_pdf import RapportPDF
from interface.page_telephone import PageTelephone


class PerformanceTrail(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Performance trail",
            onglets=[
                ("🏔️ Montées & VAM", MonteesVAM),
                ("⚙️ Allure ajustée", AllureAjustee),
                ("🔋 Résistance à la fatigue", ResistanceFatigue),
                ("⚡ Efficacité", EfficaciteCourse),
                ("⛰️ Terrain", TerrainPente),
                ("🌦️ Météo & performance", MeteoPerformance),
                ("🎯 Forme pour ma course", FormeDistance),
            ],
            athlete_id_initial=athlete_id_initial,
        )


class BilansObjectifs(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Bilans & objectifs",
            onglets=[
                ("🧮 Totaux", TotauxPeriodes),
                ("🔀 Comparer", ComparerPeriodes),
                ("🏆 Objectifs de l'année", ObjectifsAnnuels),
                ("🧪 Planifier la charge", PlanifierCharge),
                ("📄 Rapport PDF", RapportPDF),
                ("📱 Page téléphone", PageTelephone),
                ("🖼️ Affiche de l'année", AfficheAnnuelle),
            ],
            athlete_id_initial=athlete_id_initial,
        )
