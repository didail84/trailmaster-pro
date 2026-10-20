from datetime import date as _date

from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog

from interface.ecran_liste import EcranListe, Champ
from interface.fit_utils import extraire_signaux_recuperation
from interface.calendrier_sommeil import ouvrir_calendrier_sommeil
from data.database import enregistrer_signal_recuperation, obtenir_signaux_recuperation_recents
from data.sommeil_auto import combler_sommeil_manquant


def _importer_signaux_recuperation(ecran):
    athlete_id = ecran.athlete_selectionne_id()
    if athlete_id is None:
        QMessageBox.information(
            ecran, "Athlète requis",
            "Sélectionne d'abord un athlète pour rattacher les signaux importés."
        )
        return

    chemin, _ = QFileDialog.getOpenFileName(
        ecran, "Choisir un fichier .FIT", "", "Fichiers FIT (*.fit)"
    )
    if not chemin:
        return

    signaux = extraire_signaux_recuperation(chemin)

    if signaux["hrv_ms"] is None and signaux["stress_moyen"] is None:
        QMessageBox.information(
            ecran, "Aucun signal trouvé",
            "Ce fichier ne contient ni HRV ni stress exploitable — c'est fréquent pour un "
            "simple enregistrement d'activité GPS. Ces signaux viennent plutôt des fichiers "
            "de suivi quotidien d'un export complet Garmin (dossier \"monitoring\")."
        )
        return

    date_defaut = signaux["date"].isoformat() if signaux["date"] else _date.today().isoformat()
    date_texte, ok = QInputDialog.getText(
        ecran, "Date du signal",
        "Date à laquelle rattacher ce signal (AAAA-MM-JJ) :",
        text=date_defaut,
    )
    if not ok or not date_texte.strip():
        return

    enregistrer_signal_recuperation(
        athlete_id, date_texte.strip(), signaux["hrv_ms"], signaux["stress_moyen"], chemin,
    )

    morceaux = []
    if signaux["hrv_ms"] is not None:
        morceaux.append(f"HRV ≈ {signaux['hrv_ms']} ms")
    if signaux["stress_moyen"] is not None:
        morceaux.append(f"stress moyen ≈ {signaux['stress_moyen']}/100")
    QMessageBox.information(
        ecran, "Signal importé",
        "Enregistré pour le " + date_texte.strip() + " : " + ", ".join(morceaux) +
        ".\nCe signal affine légèrement le score de forme du jour (Analyses & Forme)."
    )


def _ouvrir_calendrier(ecran):
    ouvrir_calendrier_sommeil(ecran, ecran.athlete_selectionne_id())


class Sommeil(EcranListe):

    def __init__(self, athlete_id_initial=None):
        # Poursuite automatique du remplissage (rythme habituel déclaré)
        # jusqu'à hier inclus, à chaque ouverture de l'écran — plus
        # besoin de redemander un rattrapage de temps en temps.
        combler_sommeil_manquant()

        champs = [
            Champ("date", "Date", "date", obligatoire=True),
            Champ("heure_coucher", "Heure coucher", "texte"),
            Champ("heure_lever", "Heure lever", "texte"),
            Champ("duree_heures", "Durée (h)", "decimal"),
            Champ("qualite", "Qualité (1-5)", "entier"),
            Champ("reveils_nombre", "Réveils", "entier"),
            Champ("notes", "Notes", "texte_long"),
        ]
        super().__init__(
            titre="Sommeil",
            sous_titre="Suivi du sommeil et de la récupération — rempli automatiquement selon ton rythme habituel",
            icone="😴",
            table_sql="sommeil",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="date DESC",
            bouton_extra=[
                ("📅 Voir le calendrier", _ouvrir_calendrier),
                ("📥 Importer un fichier .FIT (HRV/stress)", _importer_signaux_recuperation),
            ],
        )
