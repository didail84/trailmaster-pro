from interface.ecran_liste import EcranListe, Champ


class Nutrition(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("date", "Date", "date", obligatoire=True),
            Champ(
                "type_repas", "Repas", "choix",
                choix=["Petit-déjeuner", "Déjeuner", "Dîner", "Collation", "Pendant l'effort"],
            ),
            Champ("aliments", "Aliments", "texte_long"),
            Champ("calories", "Calories (kcal)", "decimal"),
            Champ("glucides_g", "Glucides (g)", "decimal"),
            Champ("proteines_g", "Protéines (g)", "decimal"),
            Champ("lipides_g", "Lipides (g)", "decimal"),
            Champ("hydratation_l", "Hydratation (L)", "decimal"),
            Champ("notes", "Notes", "texte_long"),
        ]
        super().__init__(
            titre="Nutrition",
            sous_titre="Suivi de l'alimentation et de l'hydratation",
            icone="🥗",
            table_sql="nutrition",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="date DESC",
        )
