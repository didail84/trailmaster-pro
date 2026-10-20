from interface.conteneur_onglets import ConteneurOnglets
from interface.analyses import Analyses
from interface.sommeil import Sommeil
from interface.bilan_ia import BilanIA
from interface.vma import VMACircuits
from interface.forme_evolution import FormeFatigue, EvolutionPerformances
from interface.recuperation_tendances import RecuperationTendances
from interface.sante_charge import SommeilRecuperation, ChargeEquilibre
from interface.coach_questions import QuestionsCoach


class AnalysesEtForme(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Analyses & Forme",
            onglets=[
                ("📊 Analyses", Analyses),
                ("📈 Forme & fatigue", FormeFatigue),
                ("📉 Évolution", EvolutionPerformances),
                ("🏃 VMA & circuits", VMACircuits),
                ("🩺 Récupération & tendances", RecuperationTendances),
                ("😴 Sommeil, HRV & cœur", SommeilRecuperation),
                ("⚖️ Charge & équilibre", ChargeEquilibre),
                ("❤️ Forme & récupération (sommeil)", Sommeil),
                ("🤖 Bilan IA", BilanIA),
                ("💬 Questions au coach", QuestionsCoach),
            ],
            athlete_id_initial=athlete_id_initial,
        )
