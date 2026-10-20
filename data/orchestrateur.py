"""
TrailMaster Pro
Bloc 35 — Orchestrateur central

Première version :
- centralise l'état de l'application
- identifie l'athlète actif
- prépare la communication entre les différents moteurs
- ne modifie aucune donnée
"""
import sqlite3
from .database import CHEMIN_BDD
from dataclasses import dataclass
from typing import Optional

from data.database import connexion


@dataclass
class EtatAthlete:
    """État minimal de l'athlète actif."""

    id: int
    nom: str
    prenom: str
    age: Optional[int]
    poids: Optional[float]
    fc_repos: Optional[int]
    fc_max: Optional[int]
    fc_seuil: Optional[int]
    vma: Optional[float]
    vo2max: Optional[float]
    niveau: Optional[str]


class Orchestrateur:
    """
    Chef d'orchestre central de TrailMaster Pro.

    Cette première version est volontairement passive :
    elle lit les données mais ne les modifie pas.
    """

    def __init__(self):
        self.athlete_actif: Optional[EtatAthlete] = None

    def charger_athlete_actif(self) -> Optional[EtatAthlete]:
        """Charge le premier athlète disponible."""

        conn = connexion()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                nom,
                prenom,
                age,
                poids,
                fc_repos,
                fc_max,
                fc_seuil,
                vma,
                vo2max,
                niveau
            FROM athletes
            ORDER BY id
            LIMIT 1
        """)

        ligne = cur.fetchone()

        conn.close()

        if ligne is None:
            self.athlete_actif = None
            return None

        self.athlete_actif = EtatAthlete(*ligne)

        return self.athlete_actif
   

    def charger_seance_planifiee(self):
        """
        Charge la séance planifiée la plus proche
        pour l'athlète actif.
        """

        athlete = self.charger_athlete_actif()

        if athlete is None:
            return None

        conn = connexion()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                athlete_id,
                date,
                type_seance,
                duree,
                distance,
                denivele,
                objectif,
                notes
            FROM planning
            WHERE athlete_id = ?
            ORDER BY ABS(
                julianday(date) - julianday('now')
            )
            LIMIT 1
            """,
            (athlete.id,)
        )

        ligne = cur.fetchone()
        conn.close()

        if ligne is None:
            return None

        return dict(ligne)
        """
        Charge la séance de planning la plus proche
        pour l'athlète actif.
        """

        athlete = self.charger_athlete_actif()

        if athlete is None:
            return None

        conn = sqlite3.connect(CHEMIN_BDD)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                athlete_id,
                date,
                type_seance,
                duree,
                distance,
                denivele,
                objectif,
                notes
            FROM planning
            WHERE athlete_id = ?
            ORDER BY ABS(julianday(date) - julianday('now'))
            LIMIT 1
            """,
            (athlete.id,)
        )

        ligne = cur.fetchone()

        conn.close()

        if ligne is None:
            return None

    def charger_entrainements_recents(self, limite=7):
        """Charge les entraînements récents de l'athlète actif."""

        athlete = self.charger_athlete_actif()

        if athlete is None:
            return []

        conn = sqlite3.connect(CHEMIN_BDD)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                athlete_id,
                date,
                type,
                distance,
                denivele,
                duree,
                intensite,
                calories,
                source,
                notes
            FROM entrainements
            WHERE athlete_id = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (athlete.id, limite)
        )

        lignes = cur.fetchall()

        conn.close()

        return [dict(ligne) for ligne in lignes]
    
    def etat(self) -> dict:
        """Retourne l'état général connu par l'orchestrateur."""

        return {
            "athlete_actif": self.athlete_actif,
            "athlete_charge": self.athlete_actif is not None,
        }


if __name__ == "__main__":

    orchestrateur = Orchestrateur()

    athlete = orchestrateur.charger_athlete_actif()

    print("=== TRAILMASTER PRO — ORCHESTRATEUR ===")

    if athlete is None:
        print("Aucun athlète actif.")
    else:
        print(f"Athlète actif : {athlete.prenom} {athlete.nom}")
        print(f"ID : {athlete.id}")
        print(f"Poids : {athlete.poids} kg")
        print(f"FC repos : {athlete.fc_repos} bpm")
        print(f"FC max : {athlete.fc_max} bpm")
        print(f"VMA : {athlete.vma} km/h")
        print(f"Niveau : {athlete.niveau}")

    print("État :", orchestrateur.etat())