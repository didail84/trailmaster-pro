from interface.ecran_liste import EcranListe, Champ


class ZonesEntrainement(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("zone_numero", "Zone n°", "entier", obligatoire=True),
            Champ("nom_zone", "Nom", "texte"),
            Champ("fc_min", "FC min (bpm)", "entier"),
            Champ("fc_max", "FC max (bpm)", "entier"),
            Champ("allure_min", "Allure min (min/km)", "texte"),
            Champ("allure_max", "Allure max (min/km)", "texte"),
            Champ("description", "Description", "texte_long"),
        ]
        super().__init__(
            titre="Zones d'entraînement",
            sous_titre="Zones de fréquence cardiaque et d'allure par athlète",
            icone="📈",
            table_sql="zones_entrainement",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="zone_numero ASC",
        )
