from interface.conteneur_onglets import ConteneurOnglets
from interface.import_donnees import ImportDonnees
from interface.strava_ecran import StravaEcran
from interface.nettoyage_doublons import NettoyageDoublons
from interface.parcours_gpx import ParcoursGPX
from interface.import_montre_usb import ImporterMontreUSB
from interface.garmin_ecran import GarminEcran


class ImportEtSynchro(ConteneurOnglets):

    def __init__(self, athlete_id_initial=None):
        super().__init__(
            titre="Import & Synchro",
            onglets=[
                ("📥 Import données", ImportDonnees),
                ("☁️ Garmin Connect (auto)", GarminEcran),
                ("🔗 Synchro Strava", StravaEcran),
                ("🗺️ Parcours GPX", ParcoursGPX),
                ("⌚ Montre Garmin (USB)", ImporterMontreUSB),
                ("🧹 Nettoyage des doublons", NettoyageDoublons),
            ],
            athlete_id_initial=athlete_id_initial,
        )
