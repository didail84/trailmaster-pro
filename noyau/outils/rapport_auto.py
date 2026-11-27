"""
Rapport du mois automatique : le 1er du mois (ou au premier lancement
qui suit), le rapport PDF du mois écoulé est enregistré tout seul dans
le dossier choisi, et une notification le signale.

Règles seulement (aucun widget) : l'écriture du PDF reste dans
interface/rapport_pdf.py, qui sait dessiner les graphiques.
"""

from datetime import date
from pathlib import Path

from data.database import obtenir_parametre, definir_parametre

CLE_ACTIF = "rapport_mois_auto"
CLE_DOSSIER = "rapport_mois_dossier"
CLE_DERNIER = "rapport_mois_dernier"         # « AAAA-MM » du dernier mois écrit


def actif():
    return obtenir_parametre(CLE_ACTIF, "1") == "1"


def definir_actif(oui):
    definir_parametre(CLE_ACTIF, "1" if oui else "0")


def dossier():
    d = obtenir_parametre(CLE_DOSSIER)
    return Path(d) if d else Path.home() / "Documents" / "Trail Master Hub Pro" / "Rapports"


def definir_dossier(chemin):
    definir_parametre(CLE_DOSSIER, str(chemin))


def mois_precedent(aujourdhui=None):
    a = aujourdhui or date.today()
    return (a.year - 1, 12) if a.month == 1 else (a.year, a.month - 1)


def mois_a_ecrire(aujourdhui=None):
    """(annee, mois) à écrire maintenant, ou None si déjà fait ou désactivé."""
    if not actif():
        return None
    an, mo = mois_precedent(aujourdhui)
    cle = f"{an:04d}-{mo:02d}"
    if (obtenir_parametre(CLE_DERNIER) or "") >= cle:
        return None
    return an, mo


def marquer_ecrit(annee, mois):
    definir_parametre(CLE_DERNIER, f"{annee:04d}-{mois:02d}")


def nom_fichier(nom_athlete, annee, mois):
    propre = "".join(c if c.isalnum() or c in " -_" else "_" for c in (nom_athlete or "coureur")).strip()
    return f"Rapport {annee:04d}-{mois:02d} — {propre}.pdf"
