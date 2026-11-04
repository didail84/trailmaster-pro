from interface.conteneur_onglets import ConteneurOnglets, faire_groupe
from interface.analyses_avancees import ControleDonnees, MeilleursEfforts, ConditionsIntensite
from interface.analyses import Analyses
from interface.sommeil import Sommeil
from interface.bilan_ia import BilanIA
from interface.vma import VMACircuits
from interface.forme_evolution import FormeFatigue, EvolutionPerformances
from interface.recuperation_tendances import RecuperationTendances
from interface.sante_charge import SommeilRecuperation, ChargeEquilibre
from interface.coach_questions import QuestionsCoach
from interface.coach_du_jour import CoachDuJour
from interface.roadbook import RoadbookCourse


# v104 — onglets proches regroupés (les écrans sont inchangés, seule leur place change)
GROUPE_FORME = faire_groupe("Forme & récupération", [
    ("📈 Forme & fatigue", FormeFatigue),
    ("🩺 Récupération & tendances", RecuperationTendances),
    ("😴 Sommeil, HRV & cœur", SommeilRecuperation),
    ("❤️ Sommeil & forme", Sommeil),
    ("⚖️ Charge & équilibre", ChargeEquilibre),
    ("🌡️ Conditions & intensité", ConditionsIntensite),
])
GROUPE_PERFORMANCE = faire_groupe("Performance", [
    ("📉 Évolution", EvolutionPerformances),
    ("🏃 VMA & circuits", VMACircuits),
    ("⚡ Meilleurs efforts", MeilleursEfforts),
    ("🗺️ Roadbook", RoadbookCourse),
])
GROUPE_IA = faire_groupe("IA & bilans", [
    ("🤖 Bilan IA", BilanIA),
    ("💬 Questions au coach", QuestionsCoach),
])


class AnalysesEtForme(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Analyses & Forme",
            onglets=[
                ("📊 Analyses", Analyses),
                ("🎯 Coach du jour", CoachDuJour),
                ("🩺 Forme & récupération", GROUPE_FORME),
                ("🏃 Performance", GROUPE_PERFORMANCE),
                ("🤖 IA & bilans", GROUPE_IA),
                ("🧪 Données", ControleDonnees),
            ],
            athlete_id_initial=athlete_id_initial,
        )
